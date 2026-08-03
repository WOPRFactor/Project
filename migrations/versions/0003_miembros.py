"""Autorización: tabla `miembro` (Fase 11).

Aditiva. La adopción de los proyectos que ya existen no se hace acá sino en
`migraciones_datos`: necesita saber cuál es el admin, que es un dato de la app y
no del esquema.

Revision ID: 0003_miembros
Revises: 0002_identidad
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_miembros"
down_revision = "0002_identidad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "miembro" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "miembro",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False, server_default="editor"),
        sa.Column("creado_el", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
    )
    op.create_index("ix_miembro_project_id", "miembro", ["project_id"])
    op.create_index("ix_miembro_usuario_id", "miembro", ["usuario_id"])


def downgrade() -> None:
    op.drop_table("miembro")
