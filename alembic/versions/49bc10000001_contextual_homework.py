"""Bounded context, durable AI quotas and moderated homework revisions."""

from alembic import op
import sqlalchemy as sa

revision = "49bc10000001"
down_revision = "37ea12000001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("homework_sources", sa.Column("version_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "homework_sources", sa.Column("content_hash", sa.String(64), server_default="", nullable=False)
    )
    op.add_column("homework", sa.Column("operation", sa.String(10), server_default="create", nullable=False))
    op.add_column("homework", sa.Column("changes", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("homework", sa.Column("target_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_homework_target", "homework", "homework", ["target_id"], ["id"])
    op.add_column("homework", sa.Column("target_fingerprint", sa.String(64), nullable=True))
    op.add_column("homework", sa.Column("review_reason", sa.String(500), server_default="", nullable=False))
    op.create_table(
        "chat_context",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("message_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("version_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_chat_context_expires_at", "chat_context", ["expires_at"])
    op.create_table(
        "ai_daily_usage",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("calls", sa.Integer(), nullable=False),
    )


def downgrade():
    op.drop_table("ai_daily_usage")
    op.drop_index("ix_chat_context_expires_at", table_name="chat_context")
    op.drop_table("chat_context")
    for column in ["changes", "review_reason", "target_fingerprint"]:
        op.drop_column("homework", column)
    op.drop_constraint("fk_homework_target", "homework", type_="foreignkey")
    for column in ["target_id", "operation"]:
        op.drop_column("homework", column)
    op.drop_column("homework_sources", "content_hash")
    op.drop_column("homework_sources", "version_at")
