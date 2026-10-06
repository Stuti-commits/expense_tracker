"""add 'missed' to goal_status enum

Revision ID: 0002_add_goal_status_missed
Revises: 0001_core_tables
Create Date: 2026-10-06
"""
from alembic import op

revision = "0002_add_goal_status_missed"
down_revision = "0001_core_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE goal_status ADD VALUE IF NOT EXISTS 'missed'")


def downgrade() -> None:
    raise NotImplementedError(
        "Cannot cleanly remove an enum value in Postgres. "
        "Manual intervention required if you need to roll this back."
    )