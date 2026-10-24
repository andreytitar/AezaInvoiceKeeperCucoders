"""weblogin: telegram id на одноразовом коде входа с сайта

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-24 08:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("telegram_link_codes", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_link_codes", "telegram_user_id")
