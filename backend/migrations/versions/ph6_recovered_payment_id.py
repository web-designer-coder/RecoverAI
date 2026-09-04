"""phase 6 — recovery action recovered_payment_id link to new provider payment

Revision ID: ph6_recovered_payment_id
Revises: 37766bb1ab87
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'ph6_recovered_payment_id'
down_revision: Union[str, None] = '37766bb1ab87'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('recovery_actions', sa.Column('recovered_payment_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_recovery_actions_recovered_payment_id',
        'recovery_actions', 'payments',
        ['recovered_payment_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_recovery_actions_recovered_payment_id', 'recovery_actions', type_='foreignkey')
    op.drop_column('recovery_actions', 'recovered_payment_id')
