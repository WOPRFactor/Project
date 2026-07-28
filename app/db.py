"""Engine y sesión de SQLite. Único punto de acceso a datos: siempre por ORM."""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  — registra las tablas en el metadata
from . import models_base  # noqa: F401  — línea base
from .config import settings
from .migraciones import poner_al_dia
from .migraciones_datos import poner_al_dia as poner_al_dia_datos

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Crea lo que falte y pone al día una base de una versión anterior."""
    SQLModel.metadata.create_all(engine)
    poner_al_dia(engine)
    poner_al_dia_datos(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
