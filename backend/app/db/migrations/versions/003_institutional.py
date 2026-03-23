"""Institutional data persistence: flows, insiders, fund holdings."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_institutional"
down_revision: Union[str, None] = "002_schema_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fii_dii_flows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("fii_cash", sa.Numeric(18, 2), nullable=True),
        sa.Column("fii_futures", sa.Numeric(18, 2), nullable=True),
        sa.Column("dii_cash", sa.Numeric(18, 2), nullable=True),
        sa.Column("dii_futures", sa.Numeric(18, 2), nullable=True),
        sa.Column("sector_flows", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fii_dii_flows_as_of", "fii_dii_flows", ["as_of"], unique=False)

    op.create_table(
        "insider_activities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("value", sa.Numeric(18, 4), nullable=True),
        sa.Column("pledge_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insider_activities_as_of", "insider_activities", ["as_of"], unique=False)
    op.create_index("ix_insider_activities_symbol", "insider_activities", ["symbol"], unique=False)

    op.create_table(
        "fund_holdings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("fund", sa.String(length=120), nullable=False),
        sa.Column("symbol_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fund_holdings_as_of", "fund_holdings", ["as_of"], unique=False)
    op.create_index("ix_fund_holdings_fund", "fund_holdings", ["fund"], unique=False)

    # Hypertables and policies for TimescaleDB
    op.execute(
        """
        SELECT create_hypertable(
            'fii_dii_flows',
            'as_of',
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        """
        SELECT create_hypertable(
            'insider_activities',
            'as_of',
            'symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        """
        SELECT create_hypertable(
            'fund_holdings',
            'as_of',
            'fund',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE
        );
        """
    )

    # Compression and retention policies
    op.execute(
        "SELECT add_compression_policy('fii_dii_flows', INTERVAL '90 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('fii_dii_flows', INTERVAL '365 days', if_not_exists => TRUE)"
    )

    op.execute(
        "SELECT add_compression_policy('insider_activities', INTERVAL '90 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('insider_activities', INTERVAL '365 days', if_not_exists => TRUE)"
    )

    op.execute(
        "SELECT add_compression_policy('fund_holdings', INTERVAL '180 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('fund_holdings', INTERVAL '730 days', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    # Remove retention/compression policies before dropping tables
    for table in [
        "fii_dii_flows",
        "insider_activities",
        "fund_holdings",
    ]:
        op.execute(
            f"""
            DO $$ BEGIN
                PERFORM remove_retention_policy('{table}');
            EXCEPTION WHEN OTHERS THEN NULL; END $$;
            DO $$ BEGIN
                PERFORM remove_compression_policy('{table}');
            EXCEPTION WHEN OTHERS THEN NULL; END $$;
            """
        )

    op.drop_index("ix_fund_holdings_fund", table_name="fund_holdings")
    op.drop_index("ix_fund_holdings_as_of", table_name="fund_holdings")
    op.drop_table("fund_holdings")

    op.drop_index("ix_insider_activities_symbol", table_name="insider_activities")
    op.drop_index("ix_insider_activities_as_of", table_name="insider_activities")
    op.drop_table("insider_activities")

    op.drop_index("ix_fii_dii_flows_as_of", table_name="fii_dii_flows")
    op.drop_table("fii_dii_flows")
