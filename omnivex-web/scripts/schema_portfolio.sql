-- ─────────────────────────────────────────────
-- OMNIVEX — Portfolio Tracking Schema
-- Add to existing schema (run after schema.sql)
-- ─────────────────────────────────────────────

-- Current holdings (manually updated or via Schwab API)
CREATE TABLE IF NOT EXISTS holdings (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(10) NOT NULL UNIQUE,
    shares          DECIMAL(14,4) NOT NULL,
    avg_cost        DECIMAL(10,4) NOT NULL,
    current_price   DECIMAL(10,4),
    market_value    DECIMAL(14,2),
    unrealized_pnl  DECIMAL(14,2),
    unrealized_pnl_pct DECIMAL(8,4),
    tier            VARCHAR(20),
    date_entered    DATE,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Trade blotter (every executed trade)
CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    action          VARCHAR(20) NOT NULL,   -- BUY/ADD/REDUCE/REMOVE/ROTATE
    shares          DECIMAL(14,4) NOT NULL,
    price           DECIMAL(10,4) NOT NULL,
    total_value     DECIMAL(14,2),
    commission      DECIMAL(8,2) DEFAULT 0,
    omnivex_score   DECIMAL(6,2),
    tier            VARCHAR(20),
    mode            VARCHAR(20),
    rotate_from     VARCHAR(10),            -- for ROTATE actions
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Daily portfolio snapshots (for performance tracking)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              SERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL UNIQUE,
    total_value     DECIMAL(14,2) NOT NULL,
    cash            DECIMAL(14,2) DEFAULT 0,
    invested_value  DECIMAL(14,2),
    daily_pnl       DECIMAL(14,2),
    daily_pnl_pct   DECIMAL(8,4),
    total_pnl       DECIMAL(14,2),
    total_pnl_pct   DECIMAL(8,4),
    spy_daily_pct   DECIMAL(8,4),
    -- Tier breakdown
    smart_core_pct  DECIMAL(8,4),
    tactical_pct    DECIMAL(8,4),
    speculative_pct DECIMAL(8,4),
    cash_pct        DECIMAL(8,4),
    -- Mode at time of snapshot
    mode            VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Tier performance tracking (rolling)
CREATE TABLE IF NOT EXISTS tier_performance (
    id              SERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL,
    tier            VARCHAR(20) NOT NULL,
    return_pct      DECIMAL(8,4),
    return_vs_spy   DECIMAL(8,4),
    num_positions   INTEGER,
    avg_score       DECIMAL(6,2),
    UNIQUE(snapshot_date, tier)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON portfolio_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_tier_perf_date ON tier_performance(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker);

-- Allocator output: daily target book and rebalance plan
CREATE TABLE IF NOT EXISTS portfolio_target_summary (
    run_date                 DATE PRIMARY KEY,
    mode                     VARCHAR(20) NOT NULL,
    portfolio_base_value     DECIMAL(14,2),
    current_cash             DECIMAL(14,2),
    target_cash_pct          DECIMAL(8,4),
    target_smart_core_pct    DECIMAL(8,4),
    target_tactical_pct      DECIMAL(8,4),
    target_speculative_pct   DECIMAL(8,4),
    current_smart_core_pct   DECIMAL(8,4),
    current_tactical_pct     DECIMAL(8,4),
    current_speculative_pct  DECIMAL(8,4),
    current_cash_pct         DECIMAL(8,4),
    target_invested_pct      DECIMAL(8,4),
    estimated_turnover_pct   DECIMAL(8,4),
    max_positions            INTEGER,
    notes                    TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_targets (
    id                       SERIAL PRIMARY KEY,
    run_date                 DATE NOT NULL REFERENCES runs(run_date) ON DELETE CASCADE,
    ticker                   VARCHAR(10) NOT NULL,
    sector                   VARCHAR(100),
    tier                     VARCHAR(20),
    sleeve                   VARCHAR(20),
    rank_in_sleeve           INTEGER,
    action                   VARCHAR(20),
    omnivex_score            DECIMAL(10,2),
    signal_conf              DECIMAL(10,2),
    suggested_weight_pct     DECIMAL(10,4),
    target_weight_pct        DECIMAL(10,4) NOT NULL,
    held                     BOOLEAN DEFAULT FALSE,
    reason                   TEXT,
    flags                    TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(run_date, ticker)
);

CREATE TABLE IF NOT EXISTS rebalance_recommendations (
    id                       SERIAL PRIMARY KEY,
    run_date                 DATE NOT NULL REFERENCES runs(run_date) ON DELETE CASCADE,
    ticker                   VARCHAR(10) NOT NULL,
    sector                   VARCHAR(100),
    tier                     VARCHAR(20),
    action                   VARCHAR(20),
    recommendation           VARCHAR(20) NOT NULL,
    recommendation_reason    TEXT,
    omnivex_score            DECIMAL(10,2),
    signal_conf              DECIMAL(10,2),
    current_weight_pct       DECIMAL(10,4),
    target_weight_pct        DECIMAL(10,4),
    current_value            DECIMAL(14,2),
    target_value             DECIMAL(14,2),
    delta_weight_pct         DECIMAL(10,4),
    delta_value              DECIMAL(14,2),
    held                     BOOLEAN DEFAULT FALSE,
    sleeve                   VARCHAR(20),
    flags                    TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(run_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_target_summary_run_date ON portfolio_target_summary(run_date DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_targets_run_date ON portfolio_targets(run_date DESC, target_weight_pct DESC);
CREATE INDEX IF NOT EXISTS idx_rebalance_recommendations_run_date ON rebalance_recommendations(run_date DESC, recommendation);
