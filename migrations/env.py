"""Entorno de Alembic. La URL sale de la config de la app, no del .ini.

Así `WOPR_DB` manda en un solo lugar: la app, los tests y las migraciones
apuntan siempre a la misma base sin que haya que sincronizar dos archivos.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from app import models, models_auth, models_base  # noqa: F401 — registra las tablas
from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.db_url)

# El logging solo se reconfigura cuando Alembic corre desde su CLI. La app también
# lo invoca al arrancar, y ahí `fileConfig` pisaría la configuración de logging del
# proceso en cada llamada.
if config.config_file_name is not None and not config.attributes.get("desde_la_app"):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite: los ALTER se hacen recreando la tabla
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
