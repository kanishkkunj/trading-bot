"""Create mirofish_advisories table for normalized scenario outputs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_mirofish_advisories"
down_revision: Union[str, None] = "003_institutional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mirofish_advisories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("simulation_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("scenario_bias", sa.String(length=20), nullable=False),
        sa.Column("tail_risk_score", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("narrative_confidence", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("degraded", sa.Boolean(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_mirofish_advisories_symbol", "mirofish_advisories", ["symbol"], unique=False)
    op.create_index(
        "ix_mirofish_advisories_simulation_id", "mirofish_advisories", ["simulation_id"], unique=False
    )
    op.create_index("ix_mirofish_advisories_task_id", "mirofish_advisories", ["task_id"], unique=False)
    op.create_index("ix_mirofish_advisories_report_id", "mirofish_advisories", ["report_id"], unique=False)
    op.create_index(
        "ix_mirofish_advisories_created_at", "mirofish_advisories", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_mirofish_advisories_created_at", table_name="mirofish_advisories")
    op.drop_index("ix_mirofish_advisories_report_id", table_name="mirofish_advisories")
    op.drop_index("ix_mirofish_advisories_task_id", table_name="mirofish_advisories")
    op.drop_index("ix_mirofish_advisories_simulation_id", table_name="mirofish_advisories")
    op.drop_index("ix_mirofish_advisories_symbol", table_name="mirofish_advisories")
    op.drop_table("mirofish_advisories")
