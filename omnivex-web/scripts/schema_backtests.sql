-- ─────────────────────────────────────────────
-- OMNIVEX — Backtest Schema
-- Run after schema.sql
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS backtest_runs (
    id                  SERIAL PRIMARY KEY,
    strategy_name       VARCHAR(100) NOT NULL,
    engine              VARCHAR(40) NOT NULL,
    benchmark           VARCHAR(20) DEFAULT 'SPY',
    start_date          DATE,
    end_date            DATE,
    top_n               INTEGER,
    weighting           VARCHAR(20),
    total_return_pct    DECIMAL(10,2),
    cagr_pct            DECIMAL(10,2),
    volatility_pct      DECIMAL(10,2),
    sharpe              DECIMAL(10,4),
    max_drawdown_pct    DECIMAL(10,2),
    periods             INTEGER,
    status              VARCHAR(20) DEFAULT 'COMPLETED',
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    id                      SERIAL PRIMARY KEY,
    backtest_id             INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    run_date                DATE NOT NULL,
    next_run_date           DATE NOT NULL,
    equity                  DECIMAL(14,6) NOT NULL,
    benchmark_equity        DECIMAL(14,6),
    period_return_pct       DECIMAL(10,4),
    benchmark_return_pct    DECIMAL(10,4),
    mode                    VARCHAR(20),
    holdings                INTEGER,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_positions (
    id                      SERIAL PRIMARY KEY,
    backtest_id             INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    run_date                DATE NOT NULL,
    next_run_date           DATE NOT NULL,
    ticker                  VARCHAR(10) NOT NULL,
    action                  VARCHAR(20),
    tier                    VARCHAR(20),
    omnivex_score           DECIMAL(10,2),
    suggested_weight_pct    DECIMAL(10,4),
    entry_price             DECIMAL(12,4),
    exit_price              DECIMAL(12,4),
    return_pct              DECIMAL(10,4),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at
    ON backtest_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_curve_backtest_id
    ON backtest_equity_curve(backtest_id, run_date);
CREATE INDEX IF NOT EXISTS idx_backtest_positions_backtest_id
    ON backtest_positions(backtest_id, run_date);
