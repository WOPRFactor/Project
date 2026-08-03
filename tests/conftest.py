import os
import tempfile
from datetime import date
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

# Todo lo que sigue se fija **antes** de importar la app, porque la configuración
# se lee al importar.

# La app exige WOPR_SECRET_KEY fuera de modo debug (Fase 10).
os.environ.setdefault("WOPR_SECRET_KEY", "secreto-solo-para-tests")

# El arranque de la app (`init_db`) trabaja sobre `WOPR_DB`. Sin esto apuntaría a
# la base real del usuario: cada TestClient la abriría y migraría. Los tests usan
# SQLite en memoria para sus datos; este archivo temporal es solo para que el
# arranque tenga dónde escribir.
#
# El PID va en el nombre a propósito: con una ruta fija, dos corridas simultáneas
# de la suite se pelean el lock de ese SQLite y las dos se arrastran durante horas.
_DB_DE_PRUEBA = Path(tempfile.gettempdir()) / f"wopr-tests-arranque-{os.getpid()}.db"
_DB_DE_PRUEBA.unlink(missing_ok=True)
os.environ.setdefault("WOPR_DB", str(_DB_DE_PRUEBA))


def pytest_sessionfinish(session, exitstatus):
    """No dejar archivos sueltos en el temp del sistema.

    Windows no borra un archivo que todavía está abierto, así que primero se cierra
    el engine; si igual no se puede, se deja — es un temporal con el PID en el
    nombre y no molesta a nadie.
    """
    from app.db import engine

    engine.dispose()
    for sufijo in ("", "-journal", "-wal", "-shm"):
        try:
            Path(str(_DB_DE_PRUEBA) + sufijo).unlink(missing_ok=True)
        except OSError:
            pass

from app.models import Project  # noqa: E402
from app.schemas import ProyectoIn  # noqa: E402
from app.services import projects as projects_service  # noqa: E402


@pytest.fixture(name="session")
def session_fixture():
    """SQLite en memoria: los tests de services no tocan la DB del usuario."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="proyecto")
def proyecto_fixture(session: Session) -> Project:
    return projects_service.crear(
        session,
        ProyectoIn(nombre="Proyecto de prueba", fecha_inicio=date(2026, 1, 5)),
    )


@pytest.fixture(autouse=True)
def sin_throttling():
    """El throttling del login es por proceso: se limpia entre tests."""
    from app.services import usuarios as usuarios_service

    usuarios_service.olvidar_intentos()
    yield
    usuarios_service.olvidar_intentos()
