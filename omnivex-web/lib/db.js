import { neon } from '@neondatabase/serverless'

const sql = neon(process.env.POSTGRES_URL)

// ─── Run & Scores ──────────────────────────────────────────────────────────

export async function getLatestRun() {
  const rows = await sql`SELECT * FROM runs ORDER BY run_date DESC LIMIT 1`
  return rows[0] || null
}

export async function getLatestScores() {
  const rows = await sql`
    SELECT s.* FROM scores s
    INNER JOIN (SELECT MAX(run_date) as max_date FROM runs) r
    ON s.run_date = r.max_date
    ORDER BY s.omnivex_score DESC
  `
  return rows
}

export async function getModeHistory(days = 90) {
  const rows = await sql`
    SELECT * FROM mode_history
    WHERE run_date >= CURRENT_DATE - ${days}::integer
    ORDER BY run_date ASC
  `
  return rows
}

export async function getRunHistory(days = 90) {
  const rows = await sql`
    SELECT * FROM runs
    WHERE run_date >= CURRENT_DATE - ${days}::integer
    ORDER BY run_date DESC
  `
  return rows
}

export async function getTickerHistory(ticker, days = 60) {
  const rows = await sql`
    SELECT s.run_date, s.omnivex_score, s.qtech, s.psos, s.signal_conf,
           s.action, s.tier, s.flags, r.mode
    FROM scores s JOIN runs r ON s.run_date = r.run_date
    WHERE s.ticker = ${ticker}
    AND s.run_date >= CURRENT_DATE - ${days}::integer
    ORDER BY s.run_date ASC
  `
  return rows
}

export async function getTopMovers(limit = 10) {
  const rows = await sql`
    WITH latest AS (
      SELECT ticker, omnivex_score, action, tier
      FROM scores WHERE run_date = (SELECT MAX(run_date) FROM runs)
    ),
    prev AS (
      SELECT ticker, omnivex_score FROM scores WHERE run_date = (
        SELECT MAX(run_date) FROM runs
        WHERE run_date < (SELECT MAX(run_date) FROM runs)
      )
    )
    SELECT l.ticker, l.omnivex_score, l.action, l.tier,
           l.omnivex_score - COALESCE(p.omnivex_score, l.omnivex_score) as score_delta
    FROM latest l LEFT JOIN prev p ON l.ticker = p.ticker
    ORDER BY ABS(l.omnivex_score - COALESCE(p.omnivex_score, l.omnivex_score)) DESC
    LIMIT ${limit}
  `
  return rows
}

export async function getScoreDistribution() {
  const rows = await sql`
    SELECT
      CASE
        WHEN omnivex_score >= 80 THEN 'Breakout'
        WHEN omnivex_score >= 70 THEN 'Overweight'
        WHEN omnivex_score >= 60 THEN 'Maintain'
        WHEN omnivex_score >= 50 THEN 'Underweight'
        ELSE 'Exclude'
      END as band, COUNT(*) as count
    FROM scores
    WHERE run_date = (SELECT MAX(run_date) FROM runs)
    GROUP BY band ORDER BY MIN(omnivex_score) DESC
  `
  return rows
}

// ─── Portfolio ─────────────────────────────────────────────────────────────

export async function getHoldings() {
  const rows = await sql`
    SELECT h.*, s.omnivex_score, s.action, s.qtech, s.psos, s.signal_conf
    FROM holdings h
    LEFT JOIN scores s ON s.ticker = h.ticker
      AND s.run_date = (SELECT MAX(run_date) FROM runs)
    ORDER BY h.market_value DESC NULLS LAST
  `
  return rows
}

export async function getTrades(limit = 100) {
  const rows = await sql`
    SELECT * FROM trades ORDER BY trade_date DESC, created_at DESC LIMIT ${limit}
  `
  return rows
}

export async function getPortfolioSnapshots(days = 90) {
  const rows = await sql`
    SELECT * FROM portfolio_snapshots
    WHERE snapshot_date >= CURRENT_DATE - ${days}::integer
    ORDER BY snapshot_date ASC
  `
  return rows
}

export async function getTierPerformance(days = 90) {
  const rows = await sql`
    SELECT * FROM tier_performance
    WHERE snapshot_date >= CURRENT_DATE - ${days}::integer
    ORDER BY snapshot_date ASC
  `
  return rows
}

export async function getLatestSnapshot() {
  const rows = await sql`
    SELECT * FROM portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1
  `
  return rows[0] || null
}

export async function getAllocationSummary() {
  const rows = await sql`
    SELECT
      COALESCE(h.tier, 'UNASSIGNED') as tier,
      COUNT(*) as positions,
      SUM(h.market_value) as total_value,
      SUM(h.unrealized_pnl) as total_pnl,
      AVG(s.omnivex_score) as avg_score
    FROM holdings h
    LEFT JOIN scores s ON s.ticker = h.ticker
      AND s.run_date = (SELECT MAX(run_date) FROM runs)
    GROUP BY h.tier ORDER BY total_value DESC NULLS LAST
  `
  return rows
}

export async function getPerformanceVsSpy(days = 90) {
  const rows = await sql`
    SELECT snapshot_date, total_pnl_pct, spy_daily_pct, mode,
           smart_core_pct, tactical_pct, speculative_pct, cash_pct
    FROM portfolio_snapshots
    WHERE snapshot_date >= CURRENT_DATE - ${days}::integer
    ORDER BY snapshot_date ASC
  `
  return rows
}
