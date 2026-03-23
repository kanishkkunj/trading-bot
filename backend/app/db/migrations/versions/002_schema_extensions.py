"""Schema extensions for regimes, options, order book, feature store, predictions, analytics, and risk."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_schema_extensions"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # Enums
    timeinforce_enum = postgresql.ENUM(
        "DAY", "IOC", "FOK", "GTC", "GTD", name="timeinforce", create_type=False
    )
    producttype_enum = postgresql.ENUM(
        "CASH", "INTRADAY", "MARGIN", "FUTURES", "OPTIONS", name="producttype", create_type=False
    )
    optiontype_enum = postgresql.ENUM("CALL", "PUT", name="optiontype", create_type=False)
    regimetype_enum = postgresql.ENUM(
        "BULL", "BEAR", "SIDEWAYS", "VOLATILITY_CRISIS", "LIQUIDITY_CRUNCH", name="regimetype", create_type=False
    )
    predictiontype_enum = postgresql.ENUM("CLASSIFICATION", "REGRESSION", name="predictiontype", create_type=False)

    # Ensure enum types exist before column creation (idempotent for reruns)
    op.execute("DROP TYPE IF EXISTS timeinforce")
    op.execute("DROP TYPE IF EXISTS producttype")
    op.execute("DROP TYPE IF EXISTS optiontype")
    op.execute("DROP TYPE IF EXISTS regimetype")
    op.execute("DROP TYPE IF EXISTS predictiontype")

    op.execute("CREATE TYPE timeinforce AS ENUM ('DAY', 'IOC', 'FOK', 'GTC', 'GTD')")
    op.execute("CREATE TYPE producttype AS ENUM ('CASH', 'INTRADAY', 'MARGIN', 'FUTURES', 'OPTIONS')")
    op.execute("CREATE TYPE optiontype AS ENUM ('CALL', 'PUT')")
    op.execute("CREATE TYPE regimetype AS ENUM ('BULL', 'BEAR', 'SIDEWAYS', 'VOLATILITY_CRISIS', 'LIQUIDITY_CRUNCH')")
    op.execute("CREATE TYPE predictiontype AS ENUM ('CLASSIFICATION', 'REGRESSION')")

    # Existing tables: orders
    op.add_column("orders", sa.Column("exchange", sa.String(length=50), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "time_in_force",
            timeinforce_enum,
            nullable=False,
            server_default="DAY",
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "product_type",
            producttype_enum,
            nullable=False,
            server_default="CASH",
        ),
    )
    op.add_column("orders", sa.Column("parent_order_id", sa.String(length=36), nullable=True))
    op.add_column("orders", sa.Column("client_order_id", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("regime_label", sa.String(length=50), nullable=True))
    op.add_column("orders", sa.Column("expected_slippage", sa.Numeric(precision=10, scale=4), nullable=True))
    op.add_column("orders", sa.Column("fees", sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column("orders", sa.Column("risk_score", sa.Numeric(precision=7, scale=4), nullable=True))
    op.add_column("orders", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column(
        "orders",
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Existing tables: signals
    op.add_column("signals", sa.Column("feature_set", sa.String(length=50), nullable=True))
    op.add_column("signals", sa.Column("regime_label", sa.String(length=50), nullable=True))
    op.add_column("signals", sa.Column("regime_confidence", sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column("signals", sa.Column("horizon_seconds", sa.Integer(), nullable=True))
    op.add_column("signals", sa.Column("prediction_id", sa.String(length=36), nullable=True))
    op.add_column("signals", sa.Column("expected_return", sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column("signals", sa.Column("expected_volatility", sa.Numeric(precision=10, scale=6), nullable=True))
    op.add_column("signals", sa.Column("target_price", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column("signals", sa.Column("stop_loss", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column("signals", sa.Column("risk_score", sa.Numeric(precision=7, scale=4), nullable=True))
    op.add_column(
        "signals",
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Existing tables: positions
    op.add_column("positions", sa.Column("leverage", sa.Numeric(precision=6, scale=3), nullable=True))
    op.add_column("positions", sa.Column("risk_score", sa.Numeric(precision=7, scale=4), nullable=True))
    op.add_column("positions", sa.Column("max_drawdown", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column("positions", sa.Column("exposure", sa.Numeric(precision=18, scale=4), nullable=True))
    op.add_column("positions", sa.Column("value_at_risk", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column("positions", sa.Column("regime_label", sa.String(length=50), nullable=True))
    op.add_column("positions", sa.Column("stop_loss", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column("positions", sa.Column("take_profit", sa.Numeric(precision=15, scale=4), nullable=True))
    op.add_column(
        "positions",
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # New tables
    op.create_table(
        "regimes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("regime_type", regimetype_enum, nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("detector_version", sa.String(length=50), nullable=True),
        sa.Column("symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("features_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regimes_start_time", "regimes", ["start_time"], unique=False)
    op.create_index("ix_regimes_type", "regimes", ["regime_type"], unique=False)

    op.create_table(
        "option_quotes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("underlying_symbol", sa.String(length=20), nullable=False),
        sa.Column("option_symbol", sa.String(length=40), nullable=False),
        sa.Column("expiry", sa.DateTime(), nullable=False),
        sa.Column("strike", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("option_type", optiontype_enum, nullable=False),
        sa.Column("bid", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("ask", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("bid_size", sa.Integer(), nullable=True),
        sa.Column("ask_size", sa.Integer(), nullable=True),
        sa.Column("implied_vol", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("delta", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("gamma", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("vega", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("theta", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("rho", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("underlying_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("data_source", sa.String(length=50), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("underlying_symbol", "as_of", "id"),
    )
    op.create_index("ix_option_quotes_as_of", "option_quotes", ["as_of"], unique=False)
    op.create_index(
        "ix_option_quotes_underlying_expiry",
        "option_quotes",
        ["underlying_symbol", "expiry"],
        unique=False,
    )
    op.create_index("ix_option_quotes_option_symbol", "option_quotes", ["option_symbol"], unique=False)

    op.create_table(
        "order_book_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("venue", sa.String(length=50), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("mid_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("best_bid", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("best_ask", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("spread", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("bid_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ask_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("buy_depth", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("sell_depth", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("imbalance", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("symbol", "as_of", "id"),
    )
    op.create_index(
        "ix_order_book_snapshots_symbol_as_of",
        "order_book_snapshots",
        ["symbol", "as_of"],
        unique=False,
    )
    op.create_index("ix_order_book_snapshots_as_of", "order_book_snapshots", ["as_of"], unique=False)

    op.create_table(
        "feature_store",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("feature_set", sa.String(length=50), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=True),
        sa.Column("feature_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("label_value", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("label_available", sa.Boolean(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column("regime_label", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("symbol", "as_of", "id"),
    )
    op.create_index(
        "ix_feature_store_symbol_as_of",
        "feature_store",
        ["symbol", "as_of"],
        unique=False,
    )
    op.create_index(
        "ix_feature_store_feature_set_as_of",
        "feature_store",
        ["feature_set", "as_of"],
        unique=False,
    )

    op.create_table(
        "model_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("horizon_seconds", sa.Integer(), nullable=True),
        sa.Column("prediction_type", predictiontype_enum, nullable=False),
        sa.Column("prediction_value", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("prediction_label", sa.String(length=50), nullable=True),
        sa.Column("probabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feature_set", sa.String(length=50), nullable=True),
        sa.Column("feature_store_id", sa.String(length=36), nullable=True),
        sa.Column("regime_label", sa.String(length=50), nullable=True),
        sa.Column("quality_score", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "as_of", "id"),
    )
    op.create_index(
        "ix_model_predictions_symbol_as_of",
        "model_predictions",
        ["symbol", "as_of"],
        unique=False,
    )
    op.create_index(
        "ix_model_predictions_model_version",
        "model_predictions",
        ["model_name", "model_version"],
        unique=False,
    )

    op.create_table(
        "trade_analytics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("strategy_id", sa.String(length=50), nullable=True),
        sa.Column("regime_label", sa.String(length=50), nullable=True),
        sa.Column("entry_time", sa.DateTime(), nullable=True),
        sa.Column("exit_time", sa.DateTime(), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("gross_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("net_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("pnl_pct", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("fees", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("slippage", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("holding_seconds", sa.Integer(), nullable=True),
        sa.Column("mae", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("mfe", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("risk_score", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_analytics_symbol", "trade_analytics", ["symbol"], unique=False)
    op.create_index("ix_trade_analytics_user", "trade_analytics", ["user_id"], unique=False)
    op.create_index("ix_trade_analytics_order", "trade_analytics", ["order_id"], unique=False)

    op.create_table(
        "risk_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("window", sa.String(length=20), nullable=True),
        sa.Column("volatility", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("var_95", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("cvar_95", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("beta", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("drawdown", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("exposure", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("leverage", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("stress_scenarios", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("regime_label", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("symbol", "as_of", "id"),
    )
    op.create_index("ix_risk_metrics_symbol_as_of", "risk_metrics", ["symbol", "as_of"], unique=False)

    # Hypertables and policies
    op.execute(
        """
        SELECT create_hypertable(
            'order_book_snapshots',
            'as_of',
            'symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "ALTER TABLE order_book_snapshots SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol')"
    )
    op.execute(
        "SELECT add_compression_policy('order_book_snapshots', INTERVAL '7 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('order_book_snapshots', INTERVAL '30 days', if_not_exists => TRUE)"
    )

    op.execute(
        """
        SELECT create_hypertable(
            'option_quotes',
            'as_of',
            'underlying_symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "ALTER TABLE option_quotes SET (timescaledb.compress, timescaledb.compress_segmentby = 'underlying_symbol')"
    )
    op.execute(
        "SELECT add_compression_policy('option_quotes', INTERVAL '14 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('option_quotes', INTERVAL '90 days', if_not_exists => TRUE)"
    )

    op.execute(
        """
        SELECT create_hypertable(
            'feature_store',
            'as_of',
            'symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "ALTER TABLE feature_store SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol')"
    )
    op.execute(
        "SELECT add_compression_policy('feature_store', INTERVAL '30 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('feature_store', INTERVAL '180 days', if_not_exists => TRUE)"
    )

    op.execute(
        """
        SELECT create_hypertable(
            'model_predictions',
            'as_of',
            'symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "ALTER TABLE model_predictions SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol')"
    )
    op.execute(
        "SELECT add_compression_policy('model_predictions', INTERVAL '30 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('model_predictions', INTERVAL '180 days', if_not_exists => TRUE)"
    )

    op.execute(
        """
        SELECT create_hypertable(
            'risk_metrics',
            'as_of',
            'symbol',
            number_partitions => 4,
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "ALTER TABLE risk_metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'symbol')"
    )
    op.execute(
        "SELECT add_compression_policy('risk_metrics', INTERVAL '30 days', if_not_exists => TRUE)"
    )
    op.execute(
        "SELECT add_retention_policy('risk_metrics', INTERVAL '180 days', if_not_exists => TRUE)"
    )


def downgrade() -> None:
    # Remove retention/compression policies before dropping tables
    for table in [
        "order_book_snapshots",
        "option_quotes",
        "feature_store",
        "model_predictions",
        "risk_metrics",
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

    # Drop new tables
    op.drop_index("ix_risk_metrics_symbol_as_of", table_name="risk_metrics")
    op.drop_table("risk_metrics")

    op.drop_index("ix_trade_analytics_order", table_name="trade_analytics")
    op.drop_index("ix_trade_analytics_user", table_name="trade_analytics")
    op.drop_index("ix_trade_analytics_symbol", table_name="trade_analytics")
    op.drop_table("trade_analytics")

    op.drop_index("ix_model_predictions_model_version", table_name="model_predictions")
    op.drop_index("ix_model_predictions_symbol_as_of", table_name="model_predictions")
    op.drop_table("model_predictions")

    op.drop_index("ix_feature_store_feature_set_as_of", table_name="feature_store")
    op.drop_index("ix_feature_store_symbol_as_of", table_name="feature_store")
    op.drop_table("feature_store")

    op.drop_index("ix_order_book_snapshots_as_of", table_name="order_book_snapshots")
    op.drop_index("ix_order_book_snapshots_symbol_as_of", table_name="order_book_snapshots")
    op.drop_table("order_book_snapshots")

    op.drop_index("ix_option_quotes_option_symbol", table_name="option_quotes")
    op.drop_index("ix_option_quotes_underlying_expiry", table_name="option_quotes")
    op.drop_index("ix_option_quotes_as_of", table_name="option_quotes")
    op.drop_table("option_quotes")

    op.drop_index("ix_regimes_type", table_name="regimes")
    op.drop_index("ix_regimes_start_time", table_name="regimes")
    op.drop_table("regimes")

    # Drop added columns on existing tables
    op.drop_column("positions", "extra")
    op.drop_column("positions", "take_profit")
    op.drop_column("positions", "stop_loss")
    op.drop_column("positions", "regime_label")
    op.drop_column("positions", "value_at_risk")
    op.drop_column("positions", "exposure")
    op.drop_column("positions", "max_drawdown")
    op.drop_column("positions", "risk_score")
    op.drop_column("positions", "leverage")

    op.drop_column("signals", "extra")
    op.drop_column("signals", "risk_score")
    op.drop_column("signals", "stop_loss")
    op.drop_column("signals", "target_price")
    op.drop_column("signals", "expected_volatility")
    op.drop_column("signals", "expected_return")
    op.drop_column("signals", "prediction_id")
    op.drop_column("signals", "horizon_seconds")
    op.drop_column("signals", "regime_confidence")
    op.drop_column("signals", "regime_label")
    op.drop_column("signals", "feature_set")

    op.drop_column("orders", "extra")
    op.drop_column("orders", "notes")
    op.drop_column("orders", "risk_score")
    op.drop_column("orders", "fees")
    op.drop_column("orders", "expected_slippage")
    op.drop_column("orders", "regime_label")
    op.drop_column("orders", "client_order_id")
    op.drop_column("orders", "parent_order_id")
    op.drop_column("orders", "product_type")
    op.drop_column("orders", "time_in_force")
    op.drop_column("orders", "exchange")

    # Drop enums last
    predictiontype_enum = postgresql.ENUM("CLASSIFICATION", "REGRESSION", name="predictiontype", create_type=False)
    regimetype_enum = postgresql.ENUM(
        "BULL", "BEAR", "SIDEWAYS", "VOLATILITY_CRISIS", "LIQUIDITY_CRUNCH", name="regimetype", create_type=False
    )
    optiontype_enum = postgresql.ENUM("CALL", "PUT", name="optiontype", create_type=False)
    producttype_enum = postgresql.ENUM(
        "CASH", "INTRADAY", "MARGIN", "FUTURES", "OPTIONS", name="producttype", create_type=False
    )
    timeinforce_enum = postgresql.ENUM("DAY", "IOC", "FOK", "GTC", "GTD", name="timeinforce", create_type=False)

    predictiontype_enum.drop(op.get_bind(), checkfirst=True)
    regimetype_enum.drop(op.get_bind(), checkfirst=True)
    optiontype_enum.drop(op.get_bind(), checkfirst=True)
    producttype_enum.drop(op.get_bind(), checkfirst=True)
    timeinforce_enum.drop(op.get_bind(), checkfirst=True)

