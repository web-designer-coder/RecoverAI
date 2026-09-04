"""phase 4 decision version number

Revision ID: 853a62c9269b
Revises: 7dd48c68dfd5
Create Date: 2026-08-26 17:27:58.245159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '853a62c9269b'
down_revision: Union[str, None] = '7dd48c68dfd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows (pre-versioning decisions) are backfilled per payment in
    # creation order so "current" stays consistent across the migration.
    op.add_column(
        'recovery_decisions',
        sa.Column('version_number', sa.Integer(), nullable=True),
    )
    op.execute("""
        UPDATE recovery_decisions rd
        SET version_number = sub.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY payment_id ORDER BY created_at, id
            ) AS rn
            FROM recovery_decisions
        ) sub
        WHERE rd.id = sub.id
    """)
    op.alter_column('recovery_decisions', 'version_number', nullable=False)


def downgrade() -> None:
    op.drop_column('recovery_decisions', 'version_number')
