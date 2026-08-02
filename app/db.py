"""Engine y sesión de SQLite. Único punto de acceso a datos: siempre por ORM.

Desde la Fase 10 el esquema lo versiona **Alembic** (`migrations/`), no el script
aditivo de antes. Las migraciones de datos de v1→v2 se conservan porque una base
vieja todavía puede necesitarlas al abrirse por primera vez con esta versión.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401  — registra las tablas en el metadata
from . import models_auth  # noqa: F401  — usuarios y sesiones
from . import models_base  # noqa: F401  — línea base
from .config import RAIZ, settings
from .migraciones import poner_al_dia as columnas_al_dia
from .migraciones_datos import poner_al_dia as poner_al_dia_datos
from .migraciones_datos import preparar_registro

engine = create_engine(
    settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Deja la base lista: esquema al día y migraciones de datos aplicadas."""
    preparar_registro(engine)
    _poner_esquema_al_dia()
    poner_al_dia_datos(engine)


def _poner_esquema_al_dia() -> None:
    """Alembic si está disponible; `create_all` como red de contención.

    En una base nueva `create_all` alcanza y es instantáneo; en una existente,
    Alembic aplica las revisiones que falten. Si Alembic no está instalado (un
    entorno mínimo), `create_all` deja el esquema igual al de los modelos: la app
    arranca, y solo se pierde el versionado.

    El puente con las bases v1 se mantiene: `create_all` crea tablas nuevas pero
    **no** agrega columnas a las que ya existen, así que el script aditivo sigue
    corriendo antes de sellar el baseline. Es idempotente: en una base al día no
    hace nada.
    """
    SQLModel.metadata.create_all(engine)
    columnas_al_dia(engine)
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:  # pragma: no cover — entorno sin alembic
        return

    config = Config(str(RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.db_url)
    config.attributes["desde_la_app"] = True  # que no reconfigure el logging
    # Si la base ya tenía tablas pero nunca vio Alembic, se la sella en el
    # baseline: sus revisiones ya están representadas por `create_all`.
    if "alembic_version" not in set(inspect(engine).get_table_names()):
        command.stamp(config, "head")
        return
    command.upgrade(config, "head")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
