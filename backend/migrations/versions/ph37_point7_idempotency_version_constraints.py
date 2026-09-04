"""Point 7 — idempotency / data-integrity hardening

Adds DB-level uniqueness where model comments promised it:
- recovery_actions.idempotency_key (nullable unique, safe for existing nulls)
- recovery_decisions (payment_id, version_number) composite unique

No existing duplicates found in inspection (decisions=17, actions_with_key=0).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'ph37_p7_data_integrity'
down_revision: Union[str, None] = 'merge_ph6_ph9'
depends_on: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 7A: idempotency_key unique where present (nullable safe — nulls don't count)
    op.create_unique_constraint(
        'uq_recovery_actions_idempotency_key',
        'recovery_actions',
        ['idempotency_key'],
    )
    # 7B: decision version integrity — one version per payment
    op.create_unique_constraint(
        'uq_recovery_decisions_payment_version',
        'recovery_decisions',
        ['payment_id', 'version_number'],
    )

def downgrade() -> None:
    op.drop_constraint('uq_recovery_decisions_payment_version', 'recovery_decisions', type_='unique')
    op.drop_constraint('uq_recovery_actions_idempotency_key', 'recovery_actions', type_='unique')
