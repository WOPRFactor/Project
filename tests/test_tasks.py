from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Session

from app.models import EstadoTarea
from app.schemas import DependenciaIn, TareaIn
from app.services import dependencies as dependencies_service
from app.services import schedule as schedule_service
from app.services import tasks as tasks_service
from app.services.tasks import TareaInvalida


def crear(session, proyecto, titulo, duracion=1, parent=None):
    return tasks_service.crear(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, parent_id=parent)
    )


def test_el_arbol_devuelve_niveles(session: Session, proyecto):
    padre = crear(session, proyecto, "Fase 1")
    crear(session, proyecto, "Subtarea", parent=padre.id)
    arbol = tasks_service.arbol(session, proyecto.id)
    assert [(t.titulo, nivel) for t, nivel in arbol] == [("Fase 1", 0), ("Subtarea", 1)]


def test_no_se_puede_colgar_una_tarea_de_su_descendiente(session: Session, proyecto):
    padre = crear(session, proyecto, "Padre")
    hija = crear(session, proyecto, "Hija", parent=padre.id)
    with pytest.raises(TareaInvalida):
        tasks_service.mover(session, padre.id, hija.id)


def test_no_se_puede_colgar_una_tarea_de_si_misma(session: Session, proyecto):
    tarea = crear(session, proyecto, "Sola")
    with pytest.raises(TareaInvalida):
        tasks_service.mover(session, tarea.id, tarea.id)


def test_mover_a_primer_nivel(session: Session, proyecto):
    padre = crear(session, proyecto, "Padre")
    hija = crear(session, proyecto, "Hija", parent=padre.id)
    movida = tasks_service.mover(session, hija.id, None)
    assert movida.parent_id is None


def test_borrar_arrastra_las_subtareas(session: Session, proyecto):
    padre = crear(session, proyecto, "Padre")
    crear(session, proyecto, "Hija", parent=padre.id)
    tasks_service.eliminar(session, padre.id)
    assert tasks_service.listar(session, proyecto.id) == []


def test_borrar_promoviendo_conserva_las_subtareas(session: Session, proyecto):
    padre = crear(session, proyecto, "Padre")
    crear(session, proyecto, "Hija", parent=padre.id)
    tasks_service.eliminar(session, padre.id, promover_hijas=True)
    quedan = tasks_service.listar(session, proyecto.id)
    assert [t.titulo for t in quedan] == ["Hija"]
    assert quedan[0].parent_id is None


def test_duracion_cero_no_valida():
    with pytest.raises(ValidationError):
        TareaIn(titulo="Algo", duracion=0)


def test_titulo_vacio_no_valida():
    with pytest.raises(ValidationError):
        TareaIn(titulo="  ")


def test_cambiar_estado(session: Session, proyecto):
    tarea = crear(session, proyecto, "Tarea")
    actualizada = tasks_service.cambiar_estado(session, tarea.id, EstadoTarea.hecha)
    assert actualizada.estado == EstadoTarea.hecha


def test_dependencia_calcula_fechas(session: Session, proyecto):
    a = crear(session, proyecto, "A", duracion=3)
    b = crear(session, proyecto, "B", duracion=2)
    dependencies_service.crear(session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id))
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(a.id).fin == date(2026, 1, 7)
    assert plan.get(b.id).inicio == date(2026, 1, 8)


def test_dependencia_con_lag(session: Session, proyecto):
    a = crear(session, proyecto, "A", duracion=3)
    b = crear(session, proyecto, "B")
    dependencies_service.crear(
        session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id, lag=2)
    )
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(b.id).inicio == date(2026, 1, 12)


def test_dependencia_circular_se_rechaza_y_no_se_guarda(session: Session, proyecto):
    a = crear(session, proyecto, "A")
    b = crear(session, proyecto, "B")
    dependencies_service.crear(session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id))
    with pytest.raises(TareaInvalida) as error:
        dependencies_service.crear(
            session, proyecto.id, DependenciaIn(predecessor_id=b.id, successor_id=a.id)
        )
    assert "«A»" in str(error.value) and "«B»" in str(error.value)
    assert len(dependencies_service.listar(session, proyecto.id)) == 1


def test_dependencia_sobre_un_resumen_se_rechaza(session: Session, proyecto):
    padre = crear(session, proyecto, "Padre")
    crear(session, proyecto, "Hija", parent=padre.id)
    otra = crear(session, proyecto, "Otra")
    with pytest.raises(TareaInvalida):
        dependencies_service.crear(
            session, proyecto.id, DependenciaIn(predecessor_id=padre.id, successor_id=otra.id)
        )


def test_dependencia_duplicada_se_rechaza(session: Session, proyecto):
    a = crear(session, proyecto, "A")
    b = crear(session, proyecto, "B")
    datos = DependenciaIn(predecessor_id=a.id, successor_id=b.id)
    dependencies_service.crear(session, proyecto.id, datos)
    with pytest.raises(TareaInvalida):
        dependencies_service.crear(session, proyecto.id, datos)


def test_una_tarea_no_depende_de_si_misma():
    with pytest.raises(ValidationError):
        DependenciaIn(predecessor_id=1, successor_id=1)


def test_borrar_una_tarea_borra_sus_dependencias(session: Session, proyecto):
    a = crear(session, proyecto, "A")
    b = crear(session, proyecto, "B")
    dependencies_service.crear(session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id))
    tasks_service.eliminar(session, a.id)
    assert dependencies_service.listar(session, proyecto.id) == []
