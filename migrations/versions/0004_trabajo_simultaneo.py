"""Trabajo simultáneo: versión por tarea y auditoría de cambios (Fase 12).

Aditiva y **idempotente**: en el arranque de la app, `create_all` y el puente de
columnas de v1 corren antes que Alembic, así que la tabla y la columna pueden ya
existir cuando esto se ejecuta. Se chequea antes de tocar nada.

`task.version` nace en 1 para todas las filas que ya existían: la alternativa es un
NULL que rompería la comparación de versiones justo en las tareas más viejas.

Revision ID: 0004_trabajo_simultaneo
Revises: 0003_miembros
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_trabajo_simultaneo"
down_revision = "0003_miembros"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tablas = set(inspector.get_table_names())

    if "task" in tablas and "version" not in {
        c["name"] for c in inspector.get_columns("task")
    }:
        op.add_column(
            "task",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    if "cambio" not in tablas:
        op.create_table(
            "cambio",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            # Sin FK a propósito: la tarea se puede borrar y su historia tiene que
            # quedar. Ver `models_cambio`.
            sa.Column("task_id", sa.Integer(), nullable=True),
            sa.Column("usuario_id", sa.Integer(), nullable=True),
            sa.Column("cuando", sa.DateTime(), nullable=False),
            sa.Column("etiqueta", sa.String(length=250), nullable=False, server_default=""),
            sa.Column("campo", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("antes", sa.String(length=250), nullable=False, server_default=""),
            sa.Column("despues", sa.String(length=250), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        )
        op.create_index("ix_cambio_project_id", "cambio", ["project_id"])
        op.create_index("ix_cambio_task_id", "cambio", ["task_id"])
        op.create_index("ix_cambio_usuario_id", "cambio", ["usuario_id"])
        op.create_index("ix_cambio_cuando", "cambio", ["cuando"])


def downgrade() -> None:
    op.drop_table("cambio")
    with op.batch_alter_table("task") as lote:
        lote.drop_column("version")
