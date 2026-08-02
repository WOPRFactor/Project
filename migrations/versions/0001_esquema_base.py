"""Baseline: el esquema tal como quedó al cerrar la fase 29.

No crea nada: una base existente ya lo tiene, y una nueva la crea `create_all`
al arrancar. Su razón de ser es marcar el punto de partida para que las
revisiones siguientes (identidad, permisos) se apliquen sobre terreno conocido.

Revision ID: 0001_esquema_base
Revises:
"""

from __future__ import annotations

revision = "0001_esquema_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
