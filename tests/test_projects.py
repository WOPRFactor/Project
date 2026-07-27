from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Session

from app.models import EstadoProyecto
from app.schemas import ProyectoIn
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.schemas import TareaIn


def test_crear_y_listar(session: Session):
    projects_service.crear(session, ProyectoIn(nombre="Casa", fecha_inicio=date(2026, 3, 2)))
    proyectos = projects_service.listar(session)
    assert [p.nombre for p in proyectos] == ["Casa"]


def test_los_archivados_no_aparecen_salvo_que_se_pidan(session: Session, proyecto):
    projects_service.cambiar_estado(session, proyecto.id, EstadoProyecto.archivado)
    assert projects_service.listar(session) == []
    assert len(projects_service.listar(session, incluir_archivados=True)) == 1


def test_actualizar_cambia_los_campos(session: Session, proyecto):
    datos = ProyectoIn(nombre="Nuevo nombre", fecha_inicio=date(2026, 2, 2))
    actualizado = projects_service.actualizar(session, proyecto.id, datos)
    assert actualizado.nombre == "Nuevo nombre"
    assert actualizado.fecha_inicio == date(2026, 2, 2)


def test_nombre_vacio_no_valida():
    with pytest.raises(ValidationError):
        ProyectoIn(nombre="   ", fecha_inicio=date(2026, 1, 5))


def test_eliminar_arrastra_las_tareas(session: Session, proyecto):
    tasks_service.crear(session, proyecto.id, TareaIn(titulo="Una tarea"))
    assert projects_service.eliminar(session, proyecto.id) is True
    assert tasks_service.listar(session, proyecto.id) == []
    assert projects_service.obtener(session, proyecto.id) is None
