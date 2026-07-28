"""Duración total del proyecto y criticidad de negocio.

Son dos cosas que la app tiene que mantener al día sola: el total se recalcula al
agregar o quitar tareas, y la criticidad la marca el usuario (no el motor).
"""

from datetime import date

from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import predecesoras as predecesoras_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.models import EstadoTarea


def agregar(session, proyecto, titulo, duracion=1):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion)
    )


def resumen(session, proyecto):
    return vista_service.armar(session, proyecto.id).resumen


def test_proyecto_vacio_no_tiene_duracion(session: Session, proyecto):
    assert resumen(session, proyecto).dias_habiles == 0


def test_la_duracion_sale_del_cronograma(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=3)
    b = agregar(session, proyecto, "B", duracion=2)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)

    r = resumen(session, proyecto)
    assert r.inicio == date(2026, 1, 5)
    assert r.fin == date(2026, 1, 9)
    assert r.dias_habiles == 5
    assert r.dias_corridos == 5
    assert r.semanas == 1


def test_agregar_una_tarea_encadenada_estira_el_total(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=3)
    antes = resumen(session, proyecto).dias_habiles

    b = agregar(session, proyecto, "B", duracion=4)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)

    assert resumen(session, proyecto).dias_habiles == antes + 4


def test_quitar_la_tarea_mas_larga_acorta_el_total(session: Session, proyecto):
    agregar(session, proyecto, "Corta", duracion=2)
    larga = agregar(session, proyecto, "Larga", duracion=20)
    assert resumen(session, proyecto).dias_habiles == 20

    tasks_service.eliminar(session, larga.id)
    assert resumen(session, proyecto).dias_habiles == 2


def test_la_duracion_cuenta_los_fines_de_semana_como_corridos(session: Session, proyecto):
    agregar(session, proyecto, "Dos semanas", duracion=10)
    r = resumen(session, proyecto)
    assert r.dias_habiles == 10
    assert r.dias_corridos == 12  # incluye el fin de semana del medio
    assert r.semanas == 2


def test_los_hitos_se_cuentan_aparte(session: Session, proyecto):
    agregar(session, proyecto, "Tarea", duracion=2)
    agregar(session, proyecto, "Hito", duracion=0)
    r = resumen(session, proyecto)
    assert r.tareas == 1 and r.hitos == 1


def test_el_resumen_no_cuenta_las_tareas_resumen(session: Session, proyecto):
    padre = agregar(session, proyecto, "Padre", duracion=1)
    hija = agregar(session, proyecto, "Hija", duracion=3)
    arbol_service.indentar(session, hija.id)
    assert resumen(session, proyecto).tareas == 1


def test_el_avance_sale_de_las_tareas_hechas(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=1)
    agregar(session, proyecto, "B", duracion=1)
    assert resumen(session, proyecto).avance == 0

    tasks_service.cambiar_estado(session, a.id, EstadoTarea.hecha)
    assert resumen(session, proyecto).avance == 50


# --- criticidad: la marca el usuario, no el motor ---

def test_la_criticidad_arranca_apagada(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", duracion=2)
    assert tarea.critica is False


def test_el_usuario_marca_la_criticidad(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", duracion=2)
    tasks_service.actualizar(
        session, tarea.id, TareaIn(titulo="A", duracion=2, critica=True)
    )
    assert tasks_service.obtener(session, tarea.id).critica is True


def test_la_criticidad_del_usuario_no_depende_de_la_holgura(session: Session, proyecto):
    """Una tarea con holgura de sobra puede ser crítica para el negocio igual."""
    larga = agregar(session, proyecto, "Larga", duracion=20)
    corta = agregar(session, proyecto, "Corta, pero clave", duracion=1)
    tasks_service.actualizar(
        session, corta.id, TareaIn(titulo="Corta, pero clave", duracion=1, critica=True)
    )

    filas = {f.tarea.titulo: f for f in vista_service.armar(session, proyecto.id).filas}
    clave = filas["Corta, pero clave"]
    assert clave.tarea.critica is True      # criticidad de negocio: la puso el usuario
    assert clave.holgura > 0                # holgura: la calculó el motor
    assert not clave.sin_holgura
    assert filas["Larga"].sin_holgura       # esta sí está en la ruta crítica
    assert filas["Larga"].tarea.critica is False
