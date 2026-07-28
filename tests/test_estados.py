"""Estados definidos por el usuario.

Lo que se cuida acá es el contrato con el motor: el nombre es libre, pero `es_final`
es lo único que la app mira para saber si una tarea está terminada. Un proyecto sin
estado final dejaría el avance clavado en 0 sin explicación, así que no se permite.
"""

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, select

from app.models import ColorEstado, Estado, Task
from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import estados as estados_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.services.estados import EstadoInvalido

from .test_migraciones import base_vieja, migrar_todo


def test_un_proyecto_nuevo_arranca_con_los_tres_de_siempre(session: Session, proyecto):
    nombres = [e.nombre for e in estados_service.listar(session, proyecto.id)]
    assert nombres == ["Pendiente", "En curso", "Hecha"]


def test_solo_el_ultimo_es_final(session: Session, proyecto):
    estados = estados_service.listar(session, proyecto.id)
    assert [e.es_final for e in estados] == [False, False, True]
    assert estados_service.final(session, proyecto.id).nombre == "Hecha"


def test_una_tarea_nueva_nace_en_el_estado_inicial(session: Session, proyecto):
    tarea = tasks_service.crear(session, proyecto.id, TareaIn(titulo="A"))
    assert tarea.estado_id == estados_service.inicial(session, proyecto.id).id


def test_el_usuario_agrega_un_estado_propio(session: Session, proyecto):
    estado = estados_service.crear(
        session, proyecto.id, "Bloqueada", ColorEstado.rojo, False, 25
    )
    assert estado.orden == 3
    assert [e.nombre for e in estados_service.listar(session, proyecto.id)][-1] == "Bloqueada"


def test_un_estado_propio_marcado_final_cuenta_como_terminada(session: Session, proyecto):
    """El nombre es libre; lo que manda para el avance es `es_final`."""
    cancelada = estados_service.crear(
        session, proyecto.id, "Cancelada", ColorEstado.gris, True, 100
    )
    a = arbol_service.agregar_al_final(session, proyecto.id, TareaIn(titulo="A"))
    arbol_service.agregar_al_final(session, proyecto.id, TareaIn(titulo="B"))
    tasks_service.cambiar_estado(session, a.id, cancelada.id)

    assert vista_service.armar(session, proyecto.id).resumen.avance == 50


def test_no_se_puede_quedar_sin_estado_final(session: Session, proyecto):
    hecha = estados_service.final(session, proyecto.id)
    with pytest.raises(EstadoInvalido):
        estados_service.actualizar(
            session, hecha.id, "Hecha", ColorEstado.verde, False, 100
        )


def test_se_le_puede_sacar_lo_final_si_otro_lo_toma(session: Session, proyecto):
    estados_service.crear(session, proyecto.id, "Cerrada", ColorEstado.verde, True, 100)
    hecha = estados_service.final(session, proyecto.id)
    actualizado = estados_service.actualizar(
        session, hecha.id, "Hecha", ColorEstado.verde, False, 90
    )
    assert actualizado.es_final is False


def test_borrar_un_estado_reasigna_sus_tareas(session: Session, proyecto):
    bloqueada = estados_service.crear(
        session, proyecto.id, "Bloqueada", ColorEstado.rojo, False, 0
    )
    pendiente = estados_service.inicial(session, proyecto.id)
    tarea = tasks_service.crear(session, proyecto.id, TareaIn(titulo="A"))
    tasks_service.cambiar_estado(session, tarea.id, bloqueada.id)

    estados_service.eliminar(session, bloqueada.id, pendiente.id)

    session.refresh(tarea)
    assert tarea.estado_id == pendiente.id
    assert session.get(Estado, bloqueada.id) is None


def test_no_se_borra_el_unico_estado_final(session: Session, proyecto):
    hecha = estados_service.final(session, proyecto.id)
    with pytest.raises(EstadoInvalido):
        estados_service.eliminar(session, hecha.id)


def test_un_estado_de_otro_proyecto_no_se_puede_asignar(session: Session, proyecto):
    """El id llega de un formulario: si no es de este proyecto, cae en el inicial."""
    from datetime import date

    from app.schemas import ProyectoIn
    from app.services import projects as projects_service

    ajeno = projects_service.crear(
        session, ProyectoIn(nombre="Otro", fecha_inicio=date(2026, 1, 5))
    )
    intruso = estados_service.final(session, ajeno.id)
    tarea = tasks_service.crear(session, proyecto.id, TareaIn(titulo="A"))

    tasks_service.cambiar_estado(session, tarea.id, intruso.id)

    assert tarea.estado_id == estados_service.inicial(session, proyecto.id).id


def test_borrar_el_proyecto_se_lleva_sus_estados(session: Session, proyecto):
    from app.services import projects as projects_service

    projects_service.eliminar(session, proyecto.id)
    assert estados_service.listar(session, proyecto.id) == []


# --- migración desde la v1 ---

def test_la_columna_vieja_se_convierte_en_vinculo(tmp_path):
    engine = base_vieja(tmp_path)
    with Session(engine) as session:
        session.exec(text(
            "INSERT INTO project (nombre, descripcion, fecha_inicio, estado) "
            "VALUES ('Viejo', '', '2026-01-05', 'activo')"
        ))
        for titulo, viejo in [("A", "pendiente"), ("B", "en_curso"), ("C", "hecha")]:
            session.exec(text(
                "INSERT INTO task (project_id, titulo, notas, duracion, estado, orden) "
                f"VALUES (1, '{titulo}', '', 3, '{viejo}', 0)"
            ))
        session.commit()

    migrar_todo(engine)

    with Session(engine) as session:
        por_titulo = {
            t.titulo: session.get(Estado, t.estado_id)
            for t in session.exec(select(Task))
        }
        assert por_titulo["A"].nombre == "Pendiente"
        assert por_titulo["B"].nombre == "En curso"
        assert por_titulo["C"].nombre == "Hecha"
        assert por_titulo["C"].es_final is True


def test_la_columna_vieja_desaparece(tmp_path):
    engine = base_vieja(tmp_path)
    migrar_todo(engine)
    assert "estado" not in {c["name"] for c in inspect(engine).get_columns("task")}


def test_migrar_dos_veces_no_rompe(tmp_path):
    engine = base_vieja(tmp_path)
    migrar_todo(engine)
    assert migrar_todo(engine) == []
