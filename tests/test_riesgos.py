"""Riesgos sobre un proyecto: el tilde de la grilla, el panel y lo que no se pierde."""

import pytest
from sqlmodel import Session

from app.models import EstadoRiesgo
from app.schemas import RiesgoIn, TareaIn
from app.services import arbol as arbol_service
from app.services import riesgos as riesgos_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.services.matriz import Zona
from app.services.riesgos import RiesgoInvalido


def agregar(session, proyecto, titulo="A"):
    return arbol_service.agregar_al_final(session, proyecto.id, TareaIn(titulo=titulo))


def test_un_riesgo_puede_no_colgar_de_ninguna_tarea(session: Session, proyecto):
    """«El cliente no libera el ambiente» no es de nadie en particular."""
    riesgo = riesgos_service.crear(
        session, proyecto.id, RiesgoIn(descripcion="El cliente no libera el ambiente")
    )
    assert riesgo.task_id is None
    assert riesgos_service.listar(session, proyecto.id) == [riesgo]


def test_una_tarea_puede_tener_varios_riesgos(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Uno"), tarea.id)
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Otro"), tarea.id)
    assert len(riesgos_service.de_tarea(session, tarea.id)) == 2


def test_un_riesgo_no_se_cuelga_de_una_tarea_ajena(session: Session, proyecto):
    from datetime import date

    from app.schemas import ProyectoIn
    from app.services import projects as projects_service

    ajeno = projects_service.crear(
        session, ProyectoIn(nombre="Otro", fecha_inicio=date(2026, 1, 5))
    )
    intrusa = agregar(session, ajeno)
    with pytest.raises(RiesgoInvalido):
        riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="X"), intrusa.id)


def test_la_lista_pone_lo_mas_severo_primero(session: Session, proyecto):
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Leve", probabilidad=1, impacto=1))
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Grave", probabilidad=5, impacto=5))
    assert [r.descripcion for r in riesgos_service.listar(session, proyecto.id)] == ["Grave", "Leve"]


# --- el tilde de la grilla ---

def test_tildar_crea_un_borrador_al_centro(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)

    riesgos = riesgos_service.de_tarea(session, tarea.id)
    assert len(riesgos) == 1
    assert riesgos[0].probabilidad == 3 and riesgos[0].impacto == 3


def test_la_grilla_muestra_el_tilde(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)

    fila = vista_service.armar(session, proyecto.id).filas[0]
    assert fila.tiene_riesgo is True


def test_destildar_saca_el_borrador_vacio(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, False)
    assert riesgos_service.de_tarea(session, tarea.id) == []


def test_destildar_no_borra_un_riesgo_cargado(session: Session, proyecto):
    """Un tilde no puede llevarse trabajo que alguien se tomó el trabajo de describir."""
    tarea = agregar(session, proyecto)
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Real"), tarea.id)

    with pytest.raises(RiesgoInvalido):
        riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, False)
    assert len(riesgos_service.de_tarea(session, tarea.id)) == 1


def test_tildar_dos_veces_no_duplica(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)
    assert len(riesgos_service.de_tarea(session, tarea.id)) == 1


# --- borrado de tareas ---

def test_borrar_la_tarea_no_se_lleva_el_riesgo_cargado(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Real"), tarea.id)

    tasks_service.eliminar(session, tarea.id)

    quedan = riesgos_service.listar(session, proyecto.id)
    assert len(quedan) == 1 and quedan[0].task_id is None


def test_borrar_la_tarea_se_lleva_el_borrador_vacio(session: Session, proyecto):
    tarea = agregar(session, proyecto)
    riesgos_service.marcar_tarea(session, proyecto.id, tarea.id, True)

    tasks_service.eliminar(session, tarea.id)

    assert riesgos_service.listar(session, proyecto.id) == []


def test_borrar_el_proyecto_se_lleva_sus_riesgos(session: Session, proyecto):
    from app.services import projects as projects_service

    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="X"))
    projects_service.eliminar(session, proyecto.id)
    assert riesgos_service.listar(session, proyecto.id) == []


# --- panel ---

def test_el_panel_ubica_cada_riesgo_en_su_casilla(session: Session, proyecto):
    riesgos_service.crear(
        session, proyecto.id, RiesgoIn(descripcion="Grave", probabilidad=5, impacto=4)
    )
    panel = riesgos_service.panel(session, proyecto.id)
    ubicados = [c for fila in panel.cuadrante for c in fila if c.riesgos]
    assert len(ubicados) == 1 and ubicados[0].zona is Zona.critico
    assert panel.por_zona[Zona.critico] == 1


def test_un_riesgo_cerrado_sale_del_cuadrante(session: Session, proyecto):
    """Ensuciaría la lectura: el cuadrante muestra lo que todavía puede pasar."""
    riesgos_service.crear(
        session, proyecto.id,
        RiesgoIn(descripcion="Ya no", probabilidad=5, impacto=5, estado=EstadoRiesgo.cerrado),
    )
    panel = riesgos_service.panel(session, proyecto.id)
    assert not [c for fila in panel.cuadrante for c in fila if c.riesgos]
    assert len(panel.riesgos) == 1  # sigue en el registro


def test_el_panel_cuenta_los_abiertos(session: Session, proyecto):
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="A"))
    riesgos_service.crear(
        session, proyecto.id, RiesgoIn(descripcion="B", estado=EstadoRiesgo.mitigado)
    )
    assert riesgos_service.panel(session, proyecto.id).abiertos == 1


def test_el_panel_trae_el_titulo_de_la_tarea(session: Session, proyecto):
    tarea = agregar(session, proyecto, "Búsqueda de personal")
    riesgos_service.crear(session, proyecto.id, RiesgoIn(descripcion="Tarda"), tarea.id)
    assert riesgos_service.panel(session, proyecto.id).titulos[tarea.id] == "Búsqueda de personal"
