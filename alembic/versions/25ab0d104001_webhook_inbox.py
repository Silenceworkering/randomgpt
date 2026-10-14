"""Durable webhook inbox for sleeping free web services."""

from alembic import op
import sqlalchemy as sa

revision = "25ab0d104001"
down_revision = "f048f3b324f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "telegram_inbox",
        sa.Column("update_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("update_id"),
    )
    op.create_index("ix_inbox_ready", "telegram_inbox", ["status", "available_at"])


def downgrade():
    op.drop_index("ix_inbox_ready", table_name="telegram_inbox")
    op.drop_table("telegram_inbox")
