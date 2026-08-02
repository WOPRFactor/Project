"""Identidad: tablas `usuario` y `sesion` (Fase 10).

Aditiva: no toca ninguna tabla existente, así una base con proyectos cargados
migra sin riesgo. El downgrade las borra — se pierden cuentas y sesiones, no
datos de proyectos.

Revision ID: 0002_identidad
Revises: 0001_esquema_base
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_identidad"
down_revision = "0001_esquema_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tablas = set(sa.inspect(op.get_bind()).get_table_names())

    if "usuario" not in tablas:
        op.create_table(
            "usuario",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("mail", sa.String(length=160), nullable=False),
            sa.Column("nombre", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("hash_password", sa.String(length=200), nullable=False),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("es_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "debe_cambiar_password", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column("creado_el", sa.DateTime(), nullable=False),
            sa.Column("ultimo_ingreso", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_usuario_mail", "usuario", ["mail"], unique=True)

    if "sesion" not in tablas:
        op.create_table(
            "sesion",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("token", sa.String(length=64), nullable=False),
            sa.Column("usuario_id", sa.Integer(), nullable=False),
            sa.Column("creada_el", sa.DateTime(), nullable=False),
            sa.Column("visto_el", sa.DateTime(), nullable=False),
            sa.Column("expira_el", sa.DateTime(), nullable=False),
            sa.Column("agente", sa.String(length=200), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"]),
        )
        op.create_index("ix_sesion_token", "sesion", ["token"], unique=True)
        op.create_index("ix_sesion_usuario_id", "sesion", ["usuario_id"])


def downgrade() -> None:
    op.drop_table("sesion")
    op.drop_table("usuario")
