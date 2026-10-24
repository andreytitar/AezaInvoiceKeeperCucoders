"""teams: primary + sandbox, scope existing rows to the primary team

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-24 06:20:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Enum("primary", "sandbox", name="team_kind"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_chat_title", sa.String(length=255), nullable=True),
        sa.Column("chat_bound_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_teams_one_primary", "teams", ["kind"], unique=True, postgresql_where=sa.text("kind = 'primary'")
    )
    op.create_index(
        "uq_teams_chat",
        "teams",
        ["telegram_chat_id"],
        unique=True,
        postgresql_where=sa.text("telegram_chat_id IS NOT NULL"),
    )
    op.create_index(
        "uq_teams_invite",
        "teams",
        ["invite_code"],
        unique=True,
        postgresql_where=sa.text("invite_code IS NOT NULL"),
    )
    op.execute(
        sa.text(
            "INSERT INTO teams (id, kind, name, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'primary', 'Основная команда', now(), now())"
        )
    )
    # Уже привязанный чат (app_meta) переезжает на основную команду, чтобы демо не оборвалось.
    op.execute(
        sa.text(
            """
            UPDATE teams t
            SET telegram_chat_id = m.value::bigint
            FROM app_meta m
            WHERE t.kind = 'primary' AND m.key = 'telegram_chat_id' AND m.value ~ '^-?[0-9]+$'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE teams t
            SET telegram_chat_title = m.value
            FROM app_meta m
            WHERE t.kind = 'primary' AND m.key = 'telegram_chat_title' AND t.telegram_chat_id IS NOT NULL
            """
        )
    )

    op.add_column("users", sa.Column("team_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE users SET team_id = (SELECT id FROM teams WHERE kind = 'primary')"))
    op.alter_column("users", "team_id", nullable=False)
    op.create_index("ix_users_team_id", "users", ["team_id"])
    op.create_foreign_key("fk_users_team_id", "users", "teams", ["team_id"], ["id"], ondelete="CASCADE")

    op.add_column("recurring_payments", sa.Column("team_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE recurring_payments SET team_id = (SELECT id FROM teams WHERE kind = 'primary')"))
    op.alter_column("recurring_payments", "team_id", nullable=False)
    op.create_index("ix_recurring_payments_team_id", "recurring_payments", ["team_id"])
    op.create_foreign_key(
        "fk_recurring_payments_team_id", "recurring_payments", "teams", ["team_id"], ["id"], ondelete="CASCADE"
    )

    op.add_column("audit_logs", sa.Column("team_id", sa.UUID(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE audit_logs a
            SET team_id = u.team_id
            FROM users u
            WHERE a.actor_user_id = u.id
            """
        )
    )
    op.create_index("ix_audit_logs_team_id", "audit_logs", ["team_id"])
    op.create_foreign_key("fk_audit_logs_team_id", "audit_logs", "teams", ["team_id"], ["id"], ondelete="SET NULL")

    op.add_column("budgets", sa.Column("team_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE budgets SET team_id = (SELECT id FROM teams WHERE kind = 'primary')"))
    op.alter_column("budgets", "team_id", nullable=False)
    op.create_index("ix_budgets_team_id", "budgets", ["team_id"])
    op.create_foreign_key("fk_budgets_team_id", "budgets", "teams", ["team_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("uq_budget_period_currency", "budgets", type_="unique")
    op.execute(
        sa.text(
            "ALTER TABLE budgets ADD CONSTRAINT uq_budget_period_currency "
            "UNIQUE NULLS NOT DISTINCT (team_id, period_type, year, month, currency)"
        )
    )

    op.add_column("webhook_endpoints", sa.Column("team_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE webhook_endpoints SET team_id = (SELECT id FROM teams WHERE kind = 'primary')"))
    op.alter_column("webhook_endpoints", "team_id", nullable=False)
    op.create_index("ix_webhook_endpoints_team_id", "webhook_endpoints", ["team_id"])
    op.create_foreign_key(
        "fk_webhook_endpoints_team_id", "webhook_endpoints", "teams", ["team_id"], ["id"], ondelete="CASCADE"
    )

    op.create_table(
        "telegram_pending",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )


def downgrade() -> None:
    op.drop_table("telegram_pending")
    op.drop_constraint("fk_webhook_endpoints_team_id", "webhook_endpoints", type_="foreignkey")
    op.drop_index("ix_webhook_endpoints_team_id", table_name="webhook_endpoints")
    op.drop_column("webhook_endpoints", "team_id")
    op.execute(sa.text("ALTER TABLE budgets DROP CONSTRAINT uq_budget_period_currency"))
    op.execute(
        sa.text(
            "ALTER TABLE budgets ADD CONSTRAINT uq_budget_period_currency "
            "UNIQUE NULLS NOT DISTINCT (period_type, year, month, currency)"
        )
    )
    op.drop_constraint("fk_budgets_team_id", "budgets", type_="foreignkey")
    op.drop_index("ix_budgets_team_id", table_name="budgets")
    op.drop_column("budgets", "team_id")
    op.drop_constraint("fk_audit_logs_team_id", "audit_logs", type_="foreignkey")
    op.drop_index("ix_audit_logs_team_id", table_name="audit_logs")
    op.drop_column("audit_logs", "team_id")
    op.drop_constraint("fk_recurring_payments_team_id", "recurring_payments", type_="foreignkey")
    op.drop_index("ix_recurring_payments_team_id", table_name="recurring_payments")
    op.drop_column("recurring_payments", "team_id")
    op.drop_constraint("fk_users_team_id", "users", type_="foreignkey")
    op.drop_index("ix_users_team_id", table_name="users")
    op.drop_column("users", "team_id")
    op.drop_index("uq_teams_invite", table_name="teams")
    op.drop_index("uq_teams_chat", table_name="teams")
    op.drop_index("uq_teams_one_primary", table_name="teams")
    op.drop_table("teams")
    op.execute("DROP TYPE IF EXISTS team_kind")
