"""Persist two-week subject plans independently of homework."""

from alembic import op
import sqlalchemy as sa

revision = "37ea12000001"
down_revision = "25ab0d104001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weekly_plans",
        sa.Column("group_code", sa.String(80), primary_key=True),
        sa.Column("anchor_monday", sa.Date(), nullable=False),
        sa.Column("anchor_week", sa.Integer(), nullable=False),
        sa.Column("lessons", sa.JSON(), nullable=False),
        sa.CheckConstraint("anchor_week IN (1, 2)", name="ck_weekly_anchor"),
    )


def downgrade():
    op.drop_table("weekly_plans")
