"""Una base creada por una versión anterior tiene que seguir funcionando."""

from datetime import date

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.migraciones import poner_al_dia
from app.migraciones_datos import poner_al_dia as poner_al_dia_datos
from app.schemas import TareaIn
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.schemas import ProyectoIn


AGREGADAS_DESPUES = (
    "responsable_id", "codigo", "critica", "ambito",
    "duracion_optimista", "duracion_pesimista", "estado_id",
)


# La tabla `task` tal como la creaba la v1: sin las columnas de arriba y con `estado`
# como texto. Se escribe entera en vez de ir borrando columnas porque SQLite no deja
# borrar una que participa de una foreign key, y así el escenario queda explícito.
_TASK_V1 = """
CREATE TABLE task (
    id INTEGER NOT NULL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    parent_id INTEGER REFERENCES task(id),
    titulo VARCHAR NOT NULL,
    notas VARCHAR NOT NULL DEFAULT '',
    duracion INTEGER NOT NULL DEFAULT 1,
    snet DATE,
    estado VARCHAR NOT NULL DEFAULT 'pendiente',
    orden INTEGER NOT NULL DEFAULT 0
)
"""


def base_vieja(tmp_path):
    """Una base con la forma exacta que tenía antes de los estados definibles."""
    engine = create_engine(f"sqlite:///{tmp_path / 'vieja.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conexion:
        conexion.execute(text("DROP TABLE task"))
        conexion.execute(text(_TASK_V1))
        conexion.execute(text("CREATE INDEX ix_task_project_id ON task (project_id)"))
        conexion.execute(text("CREATE INDEX ix_task_parent_id ON task (parent_id)"))
        conexion.execute(text("DROP TABLE estado"))
    return engine


def migrar_todo(engine):
    """Lo mismo que hace `init_db` al arrancar: crear, poner al día, migrar datos."""
    SQLModel.metadata.create_all(engine)
    return poner_al_dia(engine) + poner_al_dia_datos(engine)


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

    migrar_todo(engine)

    with Session(engine) as session:
        tareas = tasks_service.listar(session, 1)
        assert [t.titulo for t in tareas] == ["Tarea vieja"]
        assert tareas[0].responsable_id is None
        assert tareas[0].codigo == ""
        assert tareas[0].critica is False
        assert tareas[0].ambito.value == "proyecto"


def test_la_app_sigue_funcionando_tras_migrar(tmp_path):
    engine = base_vieja(tmp_path)
    migrar_todo(engine)
    with Session(engine) as session:
        proyecto = projects_service.crear(
            session, ProyectoIn(nombre="Después de migrar", fecha_inicio=date(2026, 1, 5))
        )
        tarea = tasks_service.crear(
            session, proyecto.id, TareaIn(titulo="Nueva", responsable="Ariel")
        )
        from app.services import contactos as contactos_service
        assert contactos_service.obtener(session, tarea.responsable_id).nombre == "Ariel"


def test_correrla_dos_veces_no_hace_nada(tmp_path):
    engine = base_vieja(tmp_path)
    assert migrar_todo(engine)  # la primera pasada aplica cambios
    assert migrar_todo(engine) == []  # la segunda no toca nada


# La tabla `riesgo` de la primera versión del registro: el responsable era texto
# suelto y no existían ni la respuesta, ni el residual, ni la revisión.
_RIESGO_V1 = """
CREATE TABLE riesgo (
    id INTEGER NOT NULL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id),
    task_id INTEGER REFERENCES task(id),
    descripcion VARCHAR NOT NULL DEFAULT '',
    probabilidad INTEGER NOT NULL DEFAULT 3,
    impacto INTEGER NOT NULL DEFAULT 3,
    mitigacion VARCHAR NOT NULL DEFAULT '',
    responsable VARCHAR NOT NULL DEFAULT '',
    estado VARCHAR NOT NULL DEFAULT 'abierto'
)
"""


def base_con_riesgos_viejos(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'riesgos.db'}")
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conexion:
        conexion.execute(text("DROP TABLE riesgo"))
        conexion.execute(text(_RIESGO_V1))
        conexion.execute(
            text("INSERT INTO project (nombre, descripcion, fecha_inicio, estado) "
                 "VALUES ('Viejo', '', '2026-01-05', 'activo')")
        )
        for nombre in ("Ariel", "ariel", ""):
            conexion.execute(
                text("INSERT INTO riesgo (project_id, descripcion, responsable) "
                     f"VALUES (1, 'Algo', '{nombre}')")
            )
    return engine


def test_el_responsable_del_riesgo_se_convierte_en_persona(tmp_path):
    """La misma regla que en las tareas: «Ariel» y «ariel» son una sola persona."""
    from app.services import contactos as contactos_service
    from app.services import riesgos as riesgos_service

    engine = base_con_riesgos_viejos(tmp_path)
    migrar_todo(engine)

    with Session(engine) as session:
        personas = contactos_service.listar(session, 1)
        assert [p.nombre for p in personas] == ["Ariel"]
        asignados = {r.responsable_id for r in riesgos_service.listar(session, 1)}
        assert asignados == {personas[0].id, None}


def test_los_riesgos_viejos_arrancan_sin_plan_ni_residual(tmp_path):
    """Los campos nuevos nacen vacíos: nadie declaró nada, y el registro lo avisa."""
    from app.services import riesgos as riesgos_service

    engine = base_con_riesgos_viejos(tmp_path)
    migrar_todo(engine)

    with Session(engine) as session:
        riesgo = riesgos_service.listar(session, 1)[0]
        assert riesgo.respuesta.value == "sin_definir"
        assert riesgo.residual_declarado is False
        assert riesgo.revisar_el is None
        assert riesgo.mitigacion_task_id is None
