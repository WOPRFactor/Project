"""Fase 12: dos personas trabajando a la vez no se pisan.

Lo que se cuida acá no es que el guardado "ande", sino que **el segundo no gane en
silencio**: la edición que llega con una versión vieja se rechaza con 409 y no se
aplica, y todo lo que sí se aplica queda anotado con quién y cuándo.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import csrf as csrf_service
from app.auth import sesion as sesion_service
from app.db import get_session
from app.main import app
from app.models import Task
from app.models_cambio import Cambio
from app.services import cambios as cambios_service
from app.services import usuarios as usuarios_service

from .test_app import CLAVE, CUENTA, celda, crear_proyecto

AJENO = "ajeno@wopr.local"


@pytest.fixture(name="mundo")
def mundo_fixture():
    """Cliente autenticado, con un proyecto y una tarea, más el engine para espiar."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app) as cliente:
        with Session(engine) as session:
            usuarios_service.crear(
                session, CUENTA, CLAVE, es_admin=True, debe_cambiar=False
            )
        cliente.post("/ingresar", data={"mail": CUENTA, "password": CLAVE})
        token = cliente.cookies.get(sesion_service.COOKIE, "")
        cliente.headers.update({csrf_service.CABECERA: csrf_service.token_de(token)})
        crear_proyecto(cliente)
        cliente.post("/proyectos/1/tareas/agregar")
        yield cliente, engine
    app.dependency_overrides.clear()


def _version(engine, task_id=1) -> int:
    with Session(engine) as session:
        return session.get(Task, task_id).version


def _titulo(engine, task_id=1) -> str:
    with Session(engine) as session:
        return session.get(Task, task_id).titulo


def test_la_segunda_edicion_concurrente_se_rechaza_y_no_se_aplica(mundo):
    cliente, engine = mundo
    leida = _version(engine)

    primera = celda(cliente, 1, codigo="1", titulo="La que llegó primero", version=leida)
    assert primera.status_code == 200
    assert _titulo(engine) == "La que llegó primero"

    # La segunda pantalla venía con la misma versión: ya no vale.
    segunda = celda(cliente, 1, codigo="1", titulo="La que llegó tarde", version=leida)
    assert segunda.status_code == 409
    assert _titulo(engine) == "La que llegó primero"  # no se aplicó
    # El cuerpo trae el tablero recargado, para ver contra qué se chocó.
    assert "La que llegó primero" in segunda.text
    assert "Alguien editó esta fila" in segunda.text


def test_la_version_sube_con_cada_cambio_real(mundo):
    cliente, engine = mundo
    inicial = _version(engine)

    celda(cliente, 1, codigo="1", titulo="Con nombre", duracion=3, version=inicial)
    despues = _version(engine)
    assert despues > inicial

    # Volver a guardar lo mismo no la mueve: si no, cualquier pantalla abierta en
    # otra máquina quedaría en conflicto sin que nadie hubiera editado nada.
    celda(cliente, 1, codigo="1", titulo="Con nombre", duracion=3, version=despues)
    assert _version(engine) == despues


def test_una_pantalla_sin_version_no_queda_trabada(mundo):
    """Una página cargada antes de que existiera el campo tiene que poder guardar."""
    cliente, engine = mundo
    assert celda(cliente, 1, codigo="1", titulo="Sin el campo").status_code == 200
    assert _titulo(engine) == "Sin el campo"


def test_el_historial_reconstruye_la_vida_de_una_tarea(mundo):
    cliente, engine = mundo
    celda(cliente, 1, codigo="1", titulo="Firmar el acta", duracion=4)
    celda(cliente, 1, codigo="1", titulo="Firmar el acta", duracion=9)
    cliente.post("/proyectos/1/tareas/1/eliminar", data={"promover": "false"})

    with Session(engine) as session:
        historia = list(
            session.exec(select(Cambio).where(Cambio.task_id == 1).order_by(Cambio.id))
        )
    resumen = [(c.campo, c.antes, c.despues) for c in historia]

    assert (cambios_service.CAMPO_TAREA, "", cambios_service.ALTA) in resumen
    assert ("Tarea", "Tarea nueva", "Firmar el acta") in resumen
    assert ("Días", "1", "4") in resumen
    assert ("Días", "4", "9") in resumen
    assert (
        cambios_service.CAMPO_TAREA,
        cambios_service.EXISTIA,
        cambios_service.BAJA,
    ) in resumen

    # Y la historia sobrevive a la tarea: es justo el caso en que más importa.
    with Session(engine) as session:
        assert session.get(Task, 1) is None
    assert all(c.usuario_id is not None for c in historia)  # quedó firmada
    assert all(c.etiqueta for c in historia)  # y nombrada, no un id huérfano


def test_el_historial_se_ve_en_pantalla(mundo):
    cliente, _ = mundo
    celda(cliente, 1, codigo="1", titulo="Relevamiento", duracion=2)

    entero = cliente.get("/proyectos/1/historial")
    assert entero.status_code == 200
    assert "Relevamiento" in entero.text

    una_sola = cliente.get("/proyectos/1/historial?tarea=1")
    assert una_sola.status_code == 200
    assert "Historial de" in una_sola.text


def test_lo_que_aplica_el_asistente_tambien_queda_firmado(mundo):
    """Lo propone el modelo, pero lo confirma una persona: la firma es de ella."""
    cliente, engine = mundo
    celda(cliente, 1, codigo="1", titulo="Etapa")
    carga = (
        '[{"tipo": "crear_tarea", "titulo": "Prueba de estrés", "duracion": 3,'
        ' "padre_wbs": "1", "critica": false, "predecesoras": ""}]'
    )
    assert cliente.post(
        "/proyectos/1/asistente/aplicar", data={"carga": carga}
    ).status_code == 200

    with Session(engine) as session:
        nueva = session.exec(
            select(Cambio).where(Cambio.despues == cambios_service.ALTA)
        ).all()
    firmadas = [c for c in nueva if "Prueba de estrés" in c.etiqueta]
    assert firmadas, "el alta del asistente no quedó en el historial"
    assert all(c.usuario_id is not None for c in firmadas)


def test_la_auditoria_no_se_puede_editar_ni_borrar(mundo):
    """Criterio de la fase: no hay ruta que toque un `Cambio`. Se mira el ruteo real,
    no la intención — una ruta nueva mal puesta acá cae sola."""
    cliente, _ = mundo
    verbos = {
        metodo
        for ruta in app.routes
        for metodo in getattr(ruta, "methods", set())
        if "/historial" in getattr(ruta, "path", "")
    }
    assert verbos <= {"GET", "HEAD"}

    # Y por las dudas, probando de verdad:
    for verbo in ("post", "put", "patch", "delete"):
        respuesta = getattr(cliente, verbo)("/proyectos/1/historial")
        assert respuesta.status_code == 405


def test_el_ajeno_no_ve_el_historial(mundo):
    """404 y no 403: un 403 confirmaría que el proyecto existe (Fase 11)."""
    cliente, engine = mundo
    with Session(engine) as session:
        usuarios_service.crear(session, AJENO, CLAVE, debe_cambiar=False)

    with TestClient(app) as otro:
        otro.post("/ingresar", data={"mail": AJENO, "password": CLAVE})
        assert otro.get("/proyectos/1/historial").status_code == 404


def test_la_base_de_la_app_esta_en_wal():
    """WAL no es un lujo: sin él, una lectura durante una escritura da «locked»."""
    from app.db import engine

    with engine.connect() as conexion:
        modo = conexion.exec_driver_sql("PRAGMA journal_mode").scalar()
        espera = conexion.exec_driver_sql("PRAGMA busy_timeout").scalar()
    assert str(modo).lower() == "wal"
    assert espera == 5000


def test_listar_pagina_de_a_tandas(session, proyecto):
    """La paginación se prueba sobre el service: 60 ediciones por HTTP para ver que
    la página 2 existe sería carísimo y no probaría nada más."""
    tarea = Task(project_id=proyecto.id, titulo="T", codigo="1")
    session.add(tarea)
    session.commit()
    session.refresh(tarea)
    for numero in range(5):
        cambios_service.registrar(session, tarea, "Días", str(numero), str(numero + 1))

    primera, total = cambios_service.listar(
        session, proyecto.id, pagina=1, por_pagina=2
    )
    segunda, _ = cambios_service.listar(session, proyecto.id, pagina=2, por_pagina=2)
    ultima, _ = cambios_service.listar(session, proyecto.id, pagina=3, por_pagina=2)

    assert total == 5
    assert len(primera) == 2 and len(segunda) == 2 and len(ultima) == 1
    # Del más nuevo al más viejo, y sin repetir filas entre páginas.
    ids = [c.id for c in primera + segunda + ultima]
    assert ids == sorted(ids, reverse=True)
    assert len(set(ids)) == 5
