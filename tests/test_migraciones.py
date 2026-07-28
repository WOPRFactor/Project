"""Una base creada por una versión anterior tiene que seguir funcionando."""

from datetime import date

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.migraciones import poner_al_dia
from app.schemas import TareaIn
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.schemas import ProyectoIn


AGREGADAS_DESPUES = ("responsable", "codigo")


def base_vieja(tmp_path):
    """Simula la base anterior: le saco las columnas agregadas después."""
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conexion:
        for indice in inspect(engine).get_indexes("task"):
            if set(indice["column_names"]) & set(AGREGADAS_DESPUES):
                conexion.execute(text(f'DROP INDEX "{indice["name"]}"'))
        for columna in AGREGADAS_DESPUES:
            conexion.execute(text(f"ALTER TABLE task DROP COLUMN {columna}"))
    return engine


def test_agrega_las_columnas_que_faltan(tmp_path):
    engine = base_vieja(tmp_path)
    presentes = {c["name"] for c in inspect(engine).get_columns("task")}
    assert not presentes & set(AGREGADAS_DESPUES)

    aplicadas = poner_al_dia(engine)

    assert {f"task.{c}" for c in AGREGADAS_DESPUES} <= set(aplicadas)
    presentes = {c["name"] for c in inspect(engine).get_columns("task")}
    assert set(AGREGADAS_DESPUES) <= presentes


def test_recrea_el_indice_de_la_columna_nueva(tmp_path):
    engine = base_vieja(tmp_path)
    poner_al_dia(engine)
    indexadas = {
        columna
        for indice in inspect(engine).get_indexes("task")
        for columna in indice["column_names"]
    }
    assert "codigo" in indexadas


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
        assert tareas[0].codigo == ""


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
    assert poner_al_dia(engine)  # la primera pasada aplica cambios
    assert poner_al_dia(engine) == []  # la segunda no toca nada
