"""add password hash to merchants

Revision ID: ph9_1_auth_password_hash
Revises: ph9_add_merchant_razorpay_fields
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'ph9_1_auth_password_hash'
down_revision = 'ph9_add_merchant_razorpay_fields'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('merchants', sa.Column('password_hash', sa.String(length=128), nullable=True))

def downgrade() -> None:
    op.drop_column('merchants', 'password_hash')
