-- ─────────────────────────────────────────────
-- OMNIVEX — Paquette Capital
-- Vercel Postgres Schema v1.0
-- Run this once in your Vercel Postgres console
-- ─────────────────────────────────────────────

-- Daily run metadata
CREATE TABLE IF NOT EXISTS runs (
    id          SERIAL PRIMARY KEY,
    run_date    DATE NOT NULL UNIQUE,
    mode        VARCHAR(20) NOT NULL,  -- ALPHA / HEDGE / CORE
    chop_guard  BOOLEAN DEFAULT FALSE,
    vix         DECIMAL(6,2),
    ad_ratio    DECIMAL(6,2),
    spy_daily_pct DECIMAL(6,2),
    spy_above_50dma  BOOLEAN,
    spy_above_200dma BOOLEAN,
    yield_curve_state VARCHAR(20),
    alpha_trigger_count  INTEGER,
    hedge_trigger_count  INTEGER,
    tickers_scored INTEGER,
    tickers_flagged INTEGER,
    tickers_buy INTEGER,
    tickers_reduce INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Per-ticker scores (one row per ticker per run)
CREATE TABLE IF NOT EXISTS scores (
    id              SERIAL PRIMARY KEY,
    run_date        DATE NOT NULL REFERENCES runs(run_date),
    ticker          VARCHAR(10) NOT NULL,
    sector          VARCHAR(50),
    industry        VARCHAR(100),
    market_cap      BIGINT,
    tier            VARCHAR(20),        -- SMART_CORE / TACTICAL / SPECULATIVE / MONITOR
    omnivex_score   DECIMAL(6,2),
    qtech           DECIMAL(6,2),
    psos_raw        DECIMAL(10,2),
    psos            DECIMAL(6,2),
    signal_conf     DECIMAL(6,2),
    action          VARCHAR(20),        -- BUY/ADD/HOLD/REDUCE/REMOVE/ROTATE/MONITOR
    suggested_weight_pct DECIMAL(5,2),
    -- QTech subcomponents
    roic_score      DECIMAL(6,2),
    peg_score       DECIMAL(6,2),
    fcf_score       DECIMAL(6,2),
    margin_score    DECIMAL(6,2),
    debt_score      DECIMAL(6,2),
    rev_growth_score DECIMAL(6,2),
    -- Signal Confidence subcomponents
    rsi_score       DECIMAL(6,2),
    momentum_score  DECIMAL(6,2),
    volume_score    DECIMAL(6,2),
    insider_score   DECIMAL(6,2),
    analyst_score   DECIMAL(6,2),
    trend_score     DECIMAL(6,2),
    -- Flags
    forensic_flag   BOOLEAN DEFAULT FALSE,
    forensic_detail TEXT,
    override_applied BOOLEAN DEFAULT FALSE,
    override_reason TEXT,
    data_quality    VARCHAR(20),
    flags           TEXT,               -- pipe-separated
    earnings_proximity_days INTEGER,
    -- Raw market data snapshot
    price           DECIMAL(10,2),
    rsi             DECIMAL(6,2),
    volume_ratio    DECIMAL(6,2),
    return_3m       DECIMAL(8,2),
    return_6m       DECIMAL(8,2),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(run_date, ticker)
);

-- Outcome tracking (updated at +1, +5, +20 days post-trade)
CREATE TABLE IF NOT EXISTS outcomes (
    id              SERIAL PRIMARY KEY,
    score_id        INTEGER REFERENCES scores(id),
    ticker          VARCHAR(10) NOT NULL,
    action_date     DATE NOT NULL,
    tracking_day    INTEGER NOT NULL,   -- 1, 5, or 20
    return_pct      DECIMAL(8,4),
    max_drawdown    DECIMAL(8,4),
    max_upside      DECIMAL(8,4),
    hit_stop_loss   BOOLEAN,
    outperformed_spy BOOLEAN,
    spy_return_pct  DECIMAL(8,4),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(score_id, tracking_day)
);

-- Mode history (daily snapshot)
CREATE TABLE IF NOT EXISTS mode_history (
    id          SERIAL PRIMARY KEY,
    run_date    DATE NOT NULL UNIQUE REFERENCES runs(run_date),
    mode        VARCHAR(20) NOT NULL,
    vix         DECIMAL(6,2),
    ad_ratio    DECIMAL(6,2),
    spy_price   DECIMAL(10,2),
    yield_curve VARCHAR(20),
    alpha_triggers INTEGER,
    hedge_triggers INTEGER,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_scores_run_date ON scores(run_date);
CREATE INDEX IF NOT EXISTS idx_scores_ticker ON scores(ticker);
CREATE INDEX IF NOT EXISTS idx_scores_action ON scores(action);
CREATE INDEX IF NOT EXISTS idx_scores_tier ON scores(tier);
CREATE INDEX IF NOT EXISTS idx_scores_omnivex_score ON scores(omnivex_score DESC);
CREATE INDEX IF NOT EXISTS idx_outcomes_ticker ON outcomes(ticker);
CREATE INDEX IF NOT EXISTS idx_mode_history_date ON mode_history(run_date);

-- ─────────────────────────────────────────────
-- SETUP COMPLETE
-- After running this, add your connection string
-- to GitHub Actions secrets as POSTGRES_URL
-- ─────────────────────────────────────────────
