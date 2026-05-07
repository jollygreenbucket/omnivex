CREATE TABLE IF NOT EXISTS research_runs (
    id                SERIAL PRIMARY KEY,
    as_of_date        DATE NOT NULL,
    frequency         VARCHAR(20) NOT NULL,
    universe_name     VARCHAR(100) NOT NULL,
    ticker_count      INTEGER,
    mode              VARCHAR(20),
    source_note       TEXT,
    strategy_version  VARCHAR(50),
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(as_of_date, universe_name, frequency)
);

CREATE TABLE IF NOT EXISTS research_scores (
    id                    SERIAL PRIMARY KEY,
    research_run_id       INTEGER NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    as_of_date            DATE NOT NULL,
    ticker                VARCHAR(10) NOT NULL,
    sector                VARCHAR(100),
    tier                  VARCHAR(20),
    omnivex_score         DECIMAL(10,2),
    qtech                 DECIMAL(10,2),
    psos                  DECIMAL(10,2),
    signal_conf           DECIMAL(10,2),
    action                VARCHAR(20),
    suggested_weight_pct  DECIMAL(10,4),
    flags                 TEXT,
    data_quality          VARCHAR(20),
    price                 DECIMAL(12,4),
    return_1m             DECIMAL(10,2),
    return_3m             DECIMAL(10,2),
    return_6m             DECIMAL(10,2),
    volume_ratio          DECIMAL(10,4),
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(research_run_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_research_runs_date
    ON research_runs(as_of_date DESC);

CREATE INDEX IF NOT EXISTS idx_research_scores_run
    ON research_scores(research_run_id, omnivex_score DESC);

CREATE INDEX IF NOT EXISTS idx_research_scores_ticker
    ON research_scores(ticker, as_of_date DESC);
