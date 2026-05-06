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

export async function getRunDetail(runDate) {
  const [run] = await sql`
    SELECT * FROM runs WHERE run_date = ${runDate}::date LIMIT 1
  `

  if (!run) return null

  const scores = await sql`
    SELECT *
    FROM scores
    WHERE run_date = ${runDate}::date
    ORDER BY omnivex_score DESC, ticker ASC
  `

  const previousRuns = await sql`
    SELECT run_date
    FROM runs
    WHERE run_date < ${runDate}::date
    ORDER BY run_date DESC
    LIMIT 1
  `
  const previousRunDate = previousRuns[0]?.run_date || null

  let movers = []
  if (previousRunDate) {
    movers = await sql`
      SELECT curr.ticker,
             curr.omnivex_score,
             curr.action,
             curr.tier,
             curr.flags,
             curr.forensic_flag,
             curr.signal_conf,
             curr.suggested_weight_pct,
             curr.omnivex_score - COALESCE(prev.omnivex_score, curr.omnivex_score) AS score_delta
      FROM scores curr
      LEFT JOIN scores prev
        ON prev.ticker = curr.ticker
       AND prev.run_date = ${previousRunDate}::date
      WHERE curr.run_date = ${runDate}::date
      ORDER BY ABS(curr.omnivex_score - COALESCE(prev.omnivex_score, curr.omnivex_score)) DESC
      LIMIT 15
    `
  }

  return {
    run,
    scores,
    previousRunDate,
    movers,
  }
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

export async function getRebalancePlan() {
  const [run, holdings, snapshot, scores] = await Promise.all([
    getLatestRun(),
    getHoldings(),
    getLatestSnapshot(),
    getLatestScores(),
  ])

  const totalHoldingsValue = holdings.reduce((sum, holding) => sum + Number(holding.market_value || 0), 0)
  const totalPortfolioValue = Number(snapshot?.total_value || 0) || totalHoldingsValue
  const cash = Number(snapshot?.cash || 0)

  if (!run || totalPortfolioValue <= 0) {
    return {
      mode: run?.mode || null,
      totalPortfolioValue,
      cash,
      rows: [],
      summary: {
        buyCount: 0,
        trimCount: 0,
        exitCount: 0,
        openCount: 0,
      },
    }
  }

  const holdingsByTicker = new Map(holdings.map(holding => [holding.ticker, holding]))
  const scoreTickers = new Set(scores.map(score => score.ticker))
  const includedScores = scores.filter(score => Number(score.suggested_weight_pct || 0) > 0 || holdingsByTicker.has(score.ticker))

  const planRows = includedScores.map(score => {
    const holding = holdingsByTicker.get(score.ticker)
    const currentValue = Number(holding?.market_value || 0)
    const currentWeightPct = totalPortfolioValue > 0 ? (currentValue / totalPortfolioValue) * 100 : 0
    const targetWeightPct = Number(score.suggested_weight_pct || 0)
    const targetValue = totalPortfolioValue * (targetWeightPct / 100)
    const deltaValue = targetValue - currentValue
    const threshold = Math.max(totalPortfolioValue * 0.0025, 100)

    let recommendation = 'HOLD'
    if (!holding && targetWeightPct > 0) {
      recommendation = 'OPEN'
    } else if (holding && targetWeightPct <= 0.01) {
      recommendation = 'EXIT'
    } else if (deltaValue > threshold) {
      recommendation = 'ADD'
    } else if (deltaValue < -threshold) {
      recommendation = 'TRIM'
    }

    return {
      ticker: score.ticker,
      sector: score.sector,
      tier: score.tier,
      action: score.action,
      omnivex_score: Number(score.omnivex_score || 0),
      signal_conf: Number(score.signal_conf || 0),
      suggested_weight_pct: targetWeightPct,
      current_weight_pct: Number(currentWeightPct.toFixed(2)),
      current_value: currentValue,
      target_value: Number(targetValue.toFixed(2)),
      delta_value: Number(deltaValue.toFixed(2)),
      recommendation,
      shares: Number(holding?.shares || 0),
      current_price: Number(holding?.current_price || 0),
      market_value: currentValue,
      flags: score.flags,
      held: Boolean(holding),
    }
  })

  for (const holding of holdings) {
    if (scoreTickers.has(holding.ticker)) continue
    const currentValue = Number(holding.market_value || 0)
    const currentWeightPct = totalPortfolioValue > 0 ? (currentValue / totalPortfolioValue) * 100 : 0
    planRows.push({
      ticker: holding.ticker,
      sector: null,
      tier: holding.tier || 'UNASSIGNED',
      action: 'REVIEW',
      omnivex_score: null,
      signal_conf: null,
      suggested_weight_pct: 0,
      current_weight_pct: Number(currentWeightPct.toFixed(2)),
      current_value: currentValue,
      target_value: 0,
      delta_value: Number((-currentValue).toFixed(2)),
      recommendation: 'EXIT',
      shares: Number(holding.shares || 0),
      current_price: Number(holding.current_price || 0),
      market_value: currentValue,
      flags: null,
      held: true,
    })
  }

  planRows.sort((a, b) => Math.abs(b.delta_value) - Math.abs(a.delta_value))

  return {
    mode: run.mode,
    totalPortfolioValue,
    cash,
    rows: planRows,
    summary: {
      buyCount: planRows.filter(row => row.recommendation === 'ADD').length,
      trimCount: planRows.filter(row => row.recommendation === 'TRIM').length,
      exitCount: planRows.filter(row => row.recommendation === 'EXIT').length,
      openCount: planRows.filter(row => row.recommendation === 'OPEN').length,
    },
  }
}

export async function getBacktestRuns(limit = 20) {
  const rows = await sql`
    SELECT *
    FROM backtest_runs
    ORDER BY created_at DESC
    LIMIT ${limit}
  `
  return rows
}

export async function getBacktestDetail(id) {
  const [run] = await sql`
    SELECT *
    FROM backtest_runs
    WHERE id = ${id}::integer
    LIMIT 1
  `
  if (!run) return null

  const [equityCurve, positions] = await Promise.all([
    sql`
      SELECT *
      FROM backtest_equity_curve
      WHERE backtest_id = ${id}::integer
      ORDER BY run_date ASC
    `,
    sql`
      SELECT *
      FROM backtest_positions
      WHERE backtest_id = ${id}::integer
      ORDER BY ABS(return_pct) DESC, run_date DESC
      LIMIT 50
    `,
  ])

  return { run, equityCurve, positions }
}
