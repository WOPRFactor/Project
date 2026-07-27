"""Una base creada por una versión anterior tiene que seguir funcionando."""

from datetime import date

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.migraciones import poner_al_dia
from app.schemas import TareaIn
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.schemas import ProyectoIn


def base_vieja(tmp_path):
    """Simula la base anterior: le saco las columnas agregadas después."""
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conexion:
        conexion.execute(text("ALTER TABLE task DROP COLUMN responsable"))
    return engine


def test_agrega_la_columna_que_falta(tmp_path):
    engine = base_vieja(tmp_path)
    assert "responsable" not in {c["name"] for c in inspect(engine).get_columns("task")}

    aplicadas = poner_al_dia(engine)

    assert "task.responsable" in aplicadas
    assert "responsable" in {c["name"] for c in inspect(engine).get_columns("task")}


def test_las_filas_viejas_quedan_con_el_default(tmp_path):
    engine = base_vieja(tmp_path)
    with Session(engine) as session:
        session.exec(
            text(
                "INSERT INTO project (nombre, descripcion, fecha_inicio, estado) "
                "VALUES ('Viejo', '', '2026-01-05', 'activo')"
            )
        )
        session.exec(
            text(
                "INSERT INTO task (project_id, titulo, notas, duracion, estado, orden) "
                "VALUES (1, 'Tarea vieja', '', 3, 'pendiente', 0)"
            )
        )
        session.commit()

    poner_al_dia(engine)

    with Session(engine) as session:
        tareas = tasks_service.listar(session, 1)
        assert [t.titulo for t in tareas] == ["Tarea vieja"]
        assert tareas[0].responsable == ""


def test_la_app_sigue_funcionando_tras_migrar(tmp_path):
    engine = base_vieja(tmp_path)
    poner_al_dia(engine)
    with Session(engine) as session:
        proyecto = projects_service.crear(
            session, ProyectoIn(nombre="Después de migrar", fecha_inicio=date(2026, 1, 5))
        )
        tarea = tasks_service.crear(
            session, proyecto.id, TareaIn(titulo="Nueva", responsable="Ariel")
        )
        assert tarea.responsable == "Ariel"


def test_correrla_dos_veces_no_hace_nada(tmp_path):
    engine = base_vieja(tmp_path)
    assert poner_al_dia(engine) == ["task.responsable"]
    assert poner_al_dia(engine) == []
