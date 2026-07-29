"""Tests que abren un navegador de verdad y hacen clic.

Existen por una razón concreta: dos bugs seguidos —el selector de columnas y la
barra de vista entera— pasaron las 444 pruebas del resto de la suite. En los dos
casos la lógica estaba bien y tenía tests; lo que estaba roto era el control, y se
había "verificado" pasando los parámetros por URL, que ejercita el servidor y saltea
la interfaz.

Se saltean solos si no hay navegador instalado, así `uv run pytest` sigue andando en
una máquina limpia. Para tenerlos: `uv run playwright install chromium`.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

CHROMIUM_DEL_ENTORNO = os.environ.get("WOPR_CHROMIUM")


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def navegador():
    playwright = pytest.importorskip("playwright.sync_api", reason="playwright no instalado")
    with playwright.sync_playwright() as p:
        try:
            navegador = p.chromium.launch(executable_path=CHROMIUM_DEL_ENTORNO or None)
        except Exception as error:  # noqa: BLE001 — cualquier fallo de arranque
            pytest.skip(f"sin navegador disponible ({type(error).__name__}); "
                        "corré `uv run playwright install chromium`")
        yield navegador
        navegador.close()


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    """Levanta la app de verdad contra una base temporal, en un hilo aparte.

    Se reapunta el engine en vez de reimportar los módulos: reimportar vuelve a
    declarar las tablas y SQLAlchemy rechaza el metadata duplicado.
    """
    from sqlmodel import create_engine

    from app import db as db_modulo
    from app.main import app

    archivo = tmp_path_factory.mktemp("navegador") / "prueba.db"
    db_modulo.engine = create_engine(
        f"sqlite:///{archivo}", connect_args={"check_same_thread": False}
    )
    db_modulo.init_db()

    puerto = _puerto_libre()
    config = uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()

    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:  # pragma: no cover — solo si el arranque falla
        pytest.skip("el servidor de prueba no arrancó")

    yield f"http://127.0.0.1:{puerto}"

    server.should_exit = True
    hilo.join(timeout=5)


@pytest.fixture
def pagina(navegador, servidor):
    contexto = navegador.new_context(viewport={"width": 1600, "height": 950})
    pagina = contexto.new_page()
    yield pagina
    contexto.close()


@pytest.fixture
def proyecto_cargado(servidor, pagina):
    """Un proyecto con dos etapas y dependencias, cargado por HTTP.

    Las duraciones son largas a propósito: con un cronograma de pocas semanas el
    timeline entra entero en pantalla y no se puede probar nada de lo que pasa al
    desplazarse —que es la mitad de los bugs que originaron estas pruebas.
    """
    import httpx

    with httpx.Client(base_url=servidor, follow_redirects=True, timeout=30) as c:
        creado = c.post("/proyectos", data={
            "nombre": f"Prueba {time.time_ns()}", "descripcion": "",
            "fecha_inicio": "2026-01-05", "estado": "activo",
        })
        pid = int(creado.url.path.rsplit("/", 1)[-1])
        c.post(f"/proyectos/{pid}/pegar", data={
            "texto": "Etapa 1\n    Relevamiento   60\n    Analisis   45\n"
                     "Etapa 2\n    Diseno   90\nHito: cierre",
        })
    _encadenar(pid, ["Analisis", "Diseno", "cierre"])
    return f"{servidor}/proyectos/{pid}"


def _encadenar(project_id: int, titulos: list[str]) -> None:
    """Le pone a cada tarea de la lista la anterior como predecesora.

    Sin dependencias no hay flechas que dibujar, y un test que apaga las flechas
    contra un Gantt que no tiene ninguna pasa sin probar nada.
    """
    from sqlmodel import Session, select

    from app import db as db_modulo
    from app.models import Task
    from app.services import predecesoras as predecesoras_service

    with Session(db_modulo.engine) as session:
        tareas = session.exec(select(Task).where(Task.project_id == project_id)).all()
        por_titulo = {t.titulo: t for t in tareas}
        orden = [por_titulo[t] for t in titulos if t in por_titulo]
        for previa, siguiente in zip(orden, orden[1:]):
            predecesoras_service.guardar(session, project_id, siguiente.id, previa.codigo)


def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures"
