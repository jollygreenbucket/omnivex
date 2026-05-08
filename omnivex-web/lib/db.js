import { neon } from '@neondatabase/serverless'

const sql = neon(process.env.POSTGRES_URL)

function toNumber(value, fallback = 0) {
  if (value == null || value === '') return fallback
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const DEFAULT_RISK_POLICY = {
  stops: {
    SMART_CORE: -0.10,
    TACTICAL: -0.12,
    SPECULATIVE: -0.15,
    UNASSIGNED: -0.12,
  },
  profitTargets: {
    SMART_CORE: { target_pct: 0.20, trim_pct: 0.25, trailing_arm_pct: 0.12 },
    TACTICAL: { target_pct: 0.18, trim_pct: 0.22, trailing_arm_pct: 0.10 },
    SPECULATIVE: { target_pct: 0.25, trim_pct: 0.30, trailing_arm_pct: 0.10 },
    UNASSIGNED: { target_pct: 0.18, trim_pct: 0.22, trailing_arm_pct: 0.10 },
  },
}

function normalizeTier(tier) {
  const value = String(tier || '').toUpperCase()
  if (value.includes('SMART')) return 'SMART_CORE'
  if (value.includes('TACTICAL')) return 'TACTICAL'
  if (value.includes('SPEC')) return 'SPECULATIVE'
  return 'UNASSIGNED'
}

function getRiskPolicy(strategyConfig) {
  const controls = strategyConfig?.config_json?.risk_controls || {}
  const takeProfit = strategyConfig?.config_json?.take_profit_rules || {}
  return {
    stops: {
      SMART_CORE: Number(controls.stop_loss_smart_core ?? DEFAULT_RISK_POLICY.stops.SMART_CORE),
      TACTICAL: Number(controls.stop_loss_tactical ?? DEFAULT_RISK_POLICY.stops.TACTICAL),
      SPECULATIVE: Number(controls.stop_loss_speculative ?? DEFAULT_RISK_POLICY.stops.SPECULATIVE),
      UNASSIGNED: DEFAULT_RISK_POLICY.stops.UNASSIGNED,
    },
    profitTargets: {
      SMART_CORE: takeProfit.smart_core || DEFAULT_RISK_POLICY.profitTargets.SMART_CORE,
      TACTICAL: takeProfit.tactical || DEFAULT_RISK_POLICY.profitTargets.TACTICAL,
      SPECULATIVE: takeProfit.speculative || DEFAULT_RISK_POLICY.profitTargets.SPECULATIVE,
      UNASSIGNED: DEFAULT_RISK_POLICY.profitTargets.UNASSIGNED,
    },
  }
}

function assessHoldingRisk(holding, strategyConfig) {
  const tier = normalizeTier(holding?.tier)
  const policy = getRiskPolicy(strategyConfig)
  const stopLossPct = Number(policy.stops[tier] ?? DEFAULT_RISK_POLICY.stops.UNASSIGNED)
  const targetRule = policy.profitTargets[tier] || DEFAULT_RISK_POLICY.profitTargets.UNASSIGNED
  const avgCost = Number(holding?.avg_cost || 0)
  const currentPrice = Number(holding?.current_price || 0)
  const pnlPct = Number(holding?.unrealized_pnl_pct || 0)
  const action = String(holding?.action || '')

  if (!(avgCost > 0) || !(currentPrice > 0)) {
    return {
      status: 'no_basis',
      label: 'No basis',
      stopLossPct,
      hardStopPrice: null,
      targetPct: Number(targetRule.target_pct),
      targetPrice: null,
      trimPct: Number(targetRule.trim_pct),
      trimPrice: null,
      trailingArmPct: Number(targetRule.trailing_arm_pct),
      distanceToStopPct: null,
      distanceToTargetPct: null,
      note: 'Average cost unavailable',
    }
  }

  const hardStopPrice = avgCost * (1 + stopLossPct)
  const targetPct = Number(targetRule.target_pct)
  const trimPct = Number(targetRule.trim_pct)
  const trailingArmPct = Number(targetRule.trailing_arm_pct)
  const targetPrice = avgCost * (1 + targetPct)
  const trimPrice = avgCost * (1 + trimPct)
  const distanceToStopPct = hardStopPrice > 0 ? ((currentPrice / hardStopPrice) - 1) * 100 : null
  const distanceToTargetPct = targetPrice > 0 ? ((targetPrice / currentPrice) - 1) * 100 : null

  let status = 'normal'
  let label = 'Normal'
  let note = 'Inside normal risk band'

  if (pnlPct <= stopLossPct * 100) {
    status = 'stop_hit'
    label = 'Stop Hit'
    note = 'Below hard stop'
  } else if (action === 'REMOVE') {
    status = 'exit_signal'
    label = 'Exit Signal'
    note = 'Model action is REMOVE'
  } else if (action === 'REDUCE') {
    status = 'trim_signal'
    label = 'Trim Signal'
    note = 'Model action is REDUCE'
  } else if (pnlPct >= trimPct * 100) {
    status = 'trim_zone'
    label = 'Trim Zone'
    note = 'Past first profit-taking band'
  } else if (pnlPct >= targetPct * 100) {
    status = 'target_hit'
    label = 'Target Hit'
    note = 'At first take-profit band'
  } else if (pnlPct >= trailingArmPct * 100) {
    status = 'trail_armed'
    label = 'Trail Armed'
    note = 'Gain large enough for trailing stop discipline'
  } else if (distanceToStopPct != null && distanceToStopPct <= 5) {
    status = 'near_stop'
    label = 'Near Stop'
    note = 'Within 5% of hard stop'
  } else if (distanceToTargetPct != null && distanceToTargetPct <= 5) {
    status = 'near_target'
    label = 'Near Target'
    note = 'Within 5% of first target'
  }

  return {
    status,
    label,
    note,
    stopLossPct,
    hardStopPrice,
    targetPct,
    targetPrice,
    trimPct,
    trimPrice,
    trailingArmPct,
    distanceToStopPct,
    distanceToTargetPct,
  }
}

// ─── Run & Scores ──────────────────────────────────────────────────────────

export async function getLatestRun() {
  const rows = await sql`SELECT * FROM runs ORDER BY run_date DESC LIMIT 1`
  return rows[0] || null
}

export async function getLatestStrategyConfig() {
  try {
    const rows = await sql`
      SELECT *
      FROM strategy_configs
      ORDER BY updated_at DESC, id DESC
      LIMIT 1
    `
    return rows[0] || null
  } catch {
    return null
  }
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
  const strategyConfig = await getLatestStrategyConfig()
  const rows = await sql`
    SELECT h.*, s.omnivex_score, s.action, s.qtech, s.psos, s.signal_conf
    FROM holdings h
    LEFT JOIN scores s ON s.ticker = h.ticker
      AND s.run_date = (SELECT MAX(run_date) FROM runs)
    ORDER BY h.market_value DESC NULLS LAST
  `
  return rows.map(row => {
    const normalized = {
      ...row,
      shares: toNumber(row.shares),
      avg_cost: toNumber(row.avg_cost),
      current_price: toNumber(row.current_price),
      market_value: toNumber(row.market_value),
      unrealized_pnl: toNumber(row.unrealized_pnl),
      unrealized_pnl_pct: toNumber(row.unrealized_pnl_pct),
      omnivex_score: row.omnivex_score == null ? null : toNumber(row.omnivex_score),
      qtech: row.qtech == null ? null : toNumber(row.qtech),
      psos: row.psos == null ? null : toNumber(row.psos),
      signal_conf: row.signal_conf == null ? null : toNumber(row.signal_conf),
    }
    return {
      ...normalized,
      risk: assessHoldingRisk(normalized, strategyConfig),
    }
  })
}

export async function upsertHolding(input) {
  const ticker = String(input?.ticker || '').trim().toUpperCase()
  const shares = Number(input?.shares)
  const avgCost = Number(input?.avgCost)
  const currentPrice = input?.currentPrice == null || input.currentPrice === ''
    ? avgCost
    : Number(input.currentPrice)
  const dateEntered = input?.dateEntered || null

  if (!ticker) throw new Error('Ticker is required')
  if (!(shares > 0)) throw new Error('Shares must be greater than 0')
  if (!(avgCost > 0)) throw new Error('Average cost must be greater than 0')
  if (!(currentPrice > 0)) throw new Error('Current price must be greater than 0')

  const latestScoreRows = await sql`
    SELECT tier
    FROM scores
    WHERE ticker = ${ticker}
      AND run_date = (SELECT MAX(run_date) FROM runs)
    LIMIT 1
  `
  const tier = latestScoreRows[0]?.tier || 'MONITOR'
  const marketValue = shares * currentPrice
  const unrealizedPnl = (currentPrice - avgCost) * shares
  const unrealizedPnlPct = avgCost > 0 ? ((currentPrice / avgCost) - 1) * 100 : 0

  const rows = await sql`
    INSERT INTO holdings (
      ticker, shares, avg_cost, current_price, market_value,
      unrealized_pnl, unrealized_pnl_pct, tier, date_entered, updated_at
    ) VALUES (
      ${ticker}, ${shares}, ${avgCost}, ${currentPrice}, ${marketValue},
      ${unrealizedPnl}, ${unrealizedPnlPct}, ${tier}, ${dateEntered}::date, NOW()
    )
    ON CONFLICT (ticker) DO UPDATE SET
      shares = EXCLUDED.shares,
      avg_cost = EXCLUDED.avg_cost,
      current_price = EXCLUDED.current_price,
      market_value = EXCLUDED.market_value,
      unrealized_pnl = EXCLUDED.unrealized_pnl,
      unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
      tier = EXCLUDED.tier,
      date_entered = COALESCE(EXCLUDED.date_entered, holdings.date_entered),
      updated_at = NOW()
    RETURNING *
  `

  const strategyConfig = await getLatestStrategyConfig()
  return {
    ...rows[0],
    risk: assessHoldingRisk(rows[0], strategyConfig),
  }
}

export async function getPortfolioTransactions(limit = 100) {
  try {
    const rows = await sql`
      SELECT *
      FROM portfolio_transactions
      ORDER BY transaction_date DESC, created_at DESC, id DESC
      LIMIT ${limit}
    `
    return rows.map(row => ({
      ...row,
      shares: row.shares == null ? null : toNumber(row.shares),
      price: row.price == null ? null : toNumber(row.price),
      amount: row.amount == null ? null : toNumber(row.amount),
    }))
  } catch (error) {
    console.warn('Portfolio transactions unavailable:', error.message)
    return []
  }
}

async function syncHoldingFromTransactions(ticker, currentPriceOverride = null) {
  const txRows = await sql`
    SELECT *
    FROM portfolio_transactions
    WHERE ticker = ${ticker}
    ORDER BY transaction_date ASC, id ASC
  `

  if (!txRows.length) {
    return null
  }

  const existingHoldingRows = await sql`
    SELECT *
    FROM holdings
    WHERE ticker = ${ticker}
    LIMIT 1
  `
  const existingHolding = existingHoldingRows[0] || null

  let shares = 0
  let totalCost = 0
  let dateEntered = null
  let lastPrice = null

  txRows.forEach(row => {
    const txType = String(row.transaction_type || '').toUpperCase()
    const txShares = toNumber(row.shares)
    const txPrice = row.price == null ? null : toNumber(row.price)
    const txAmount = row.amount == null ? null : toNumber(row.amount)

    if (!dateEntered && (txType === 'BUY' || txType === 'DRIP') && txShares > 0) {
      dateEntered = row.transaction_date
    }

    if (txPrice && txPrice > 0) {
      lastPrice = txPrice
    }

    if (txType === 'BUY' || txType === 'DRIP') {
      if (txShares <= 0) return
      shares += txShares
      totalCost += txAmount != null && txAmount > 0 ? txAmount : txShares * toNumber(txPrice)
      return
    }

    if (txType === 'SELL') {
      if (txShares <= 0 || shares <= 0) return
      const sellShares = Math.min(txShares, shares)
      const avgCost = shares > 0 ? totalCost / shares : 0
      totalCost = Math.max(0, totalCost - (avgCost * sellShares))
      shares = Math.max(0, shares - sellShares)
    }
  })

  if (shares <= 0) {
    await sql`DELETE FROM holdings WHERE ticker = ${ticker}`
    return null
  }

  const avgCost = shares > 0 ? totalCost / shares : 0
  const currentPrice = currentPriceOverride != null && currentPriceOverride !== ''
    ? toNumber(currentPriceOverride)
    : (existingHolding?.current_price != null ? toNumber(existingHolding.current_price) : (lastPrice ?? avgCost))
  const marketValue = shares * currentPrice
  const unrealizedPnl = shares * (currentPrice - avgCost)
  const unrealizedPnlPct = avgCost > 0 ? ((currentPrice / avgCost) - 1) * 100 : 0

  const latestScoreRows = await sql`
    SELECT tier
    FROM scores
    WHERE ticker = ${ticker}
      AND run_date = (SELECT MAX(run_date) FROM runs)
    LIMIT 1
  `
  const tier = latestScoreRows[0]?.tier || existingHolding?.tier || 'MONITOR'

  const rows = await sql`
    INSERT INTO holdings (
      ticker, shares, avg_cost, current_price, market_value,
      unrealized_pnl, unrealized_pnl_pct, tier, date_entered, updated_at
    ) VALUES (
      ${ticker}, ${shares}, ${avgCost}, ${currentPrice}, ${marketValue},
      ${unrealizedPnl}, ${unrealizedPnlPct}, ${tier}, ${dateEntered}::date, NOW()
    )
    ON CONFLICT (ticker) DO UPDATE SET
      shares = EXCLUDED.shares,
      avg_cost = EXCLUDED.avg_cost,
      current_price = EXCLUDED.current_price,
      market_value = EXCLUDED.market_value,
      unrealized_pnl = EXCLUDED.unrealized_pnl,
      unrealized_pnl_pct = EXCLUDED.unrealized_pnl_pct,
      tier = EXCLUDED.tier,
      date_entered = COALESCE(EXCLUDED.date_entered, holdings.date_entered),
      updated_at = NOW()
    RETURNING *
  `

  const strategyConfig = await getLatestStrategyConfig()
  return {
    ...rows[0],
    risk: assessHoldingRisk(rows[0], strategyConfig),
  }
}

export async function insertPortfolioTransaction(input) {
  const ticker = String(input?.ticker || '').trim().toUpperCase()
  const transactionType = String(input?.transactionType || '').trim().toUpperCase()
  const transactionDate = input?.transactionDate || null
  const shares = input?.shares == null || input.shares === '' ? null : Number(input.shares)
  const price = input?.price == null || input.price === '' ? null : Number(input.price)
  const amount = input?.amount == null || input.amount === '' ? null : Number(input.amount)
  const currentPrice = input?.currentPrice == null || input.currentPrice === '' ? null : Number(input.currentPrice)
  const notes = input?.notes ? String(input.notes).trim() : null

  if (!ticker) throw new Error('Ticker is required')
  if (!transactionDate) throw new Error('Transaction date is required')
  if (!['BUY', 'SELL', 'DRIP', 'DIVIDEND'].includes(transactionType)) {
    throw new Error('Transaction type must be BUY, SELL, DRIP, or DIVIDEND')
  }

  if (transactionType === 'DIVIDEND') {
    if (!(amount > 0)) throw new Error('Dividend amount must be greater than 0')
  } else {
    if (!(shares > 0)) throw new Error('Shares must be greater than 0')
    if (!(price > 0)) throw new Error('Price must be greater than 0')
  }

  const effectiveAmount = amount != null
    ? amount
    : ((shares != null && price != null) ? Number((shares * price).toFixed(2)) : null)

  const rows = await sql`
    INSERT INTO portfolio_transactions (
      transaction_date, ticker, transaction_type, shares, price, amount, notes, created_at
    ) VALUES (
      ${transactionDate}::date, ${ticker}, ${transactionType}, ${shares}, ${price}, ${effectiveAmount}, ${notes}, NOW()
    )
    RETURNING *
  `

  const holding = await syncHoldingFromTransactions(ticker, currentPrice)
  return {
    transaction: {
      ...rows[0],
      shares: rows[0].shares == null ? null : toNumber(rows[0].shares),
      price: rows[0].price == null ? null : toNumber(rows[0].price),
      amount: rows[0].amount == null ? null : toNumber(rows[0].amount),
    },
    holding,
  }
}

export async function resetPortfolioTicker(input) {
  const ticker = String(input?.ticker || '').trim().toUpperCase()
  if (!ticker) throw new Error('Ticker is required')

  const [deletedTransactions, deletedHoldings] = await Promise.all([
    sql`
      DELETE FROM portfolio_transactions
      WHERE ticker = ${ticker}
      RETURNING id
    `.catch(() => []),
    sql`
      DELETE FROM holdings
      WHERE ticker = ${ticker}
      RETURNING id
    `,
  ])

  return {
    ticker,
    deletedTransactions: Array.isArray(deletedTransactions) ? deletedTransactions.length : 0,
    deletedHoldings: Array.isArray(deletedHoldings) ? deletedHoldings.length : 0,
  }
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
  return rows.map(row => ({
    ...row,
    positions: toNumber(row.positions),
    total_value: toNumber(row.total_value),
    total_pnl: toNumber(row.total_pnl),
    avg_score: row.avg_score == null ? null : toNumber(row.avg_score),
  }))
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
  const strategyConfig = await getLatestStrategyConfig()
  const holdingBasisRows = await sql`
    SELECT ticker, avg_cost, current_price, unrealized_pnl_pct, tier, market_value, shares
    FROM holdings
  `
  const normalizedHoldings = holdingBasisRows.map(row => ({
    ...row,
    avg_cost: toNumber(row.avg_cost),
    current_price: toNumber(row.current_price),
    unrealized_pnl_pct: toNumber(row.unrealized_pnl_pct),
    market_value: toNumber(row.market_value),
    shares: toNumber(row.shares),
  }))
  const holdingBasis = new Map(normalizedHoldings.map(row => [row.ticker, row]))
  const liveHoldingsValue = normalizedHoldings.reduce((sum, row) => sum + toNumber(row.market_value), 0)
  try {
    const summaryRows = await sql`
      SELECT *
      FROM portfolio_target_summary
      ORDER BY run_date DESC
      LIMIT 1
    `
    const summary = summaryRows[0] || null

    if (summary) {
      const rows = await sql`
        SELECT *
        FROM rebalance_recommendations
        WHERE run_date = ${summary.run_date}::date
        ORDER BY
          CASE recommendation
            WHEN 'OPEN' THEN 1
            WHEN 'ADD' THEN 2
            WHEN 'TRIM' THEN 3
            WHEN 'EXIT' THEN 4
            ELSE 5
          END,
          ABS(delta_value) DESC
      `

      const latestSnapshot = await getLatestSnapshot()
      const currentCash = latestSnapshot?.cash == null ? toNumber(summary.current_cash) : toNumber(latestSnapshot.cash)
      const totalPortfolioValue =
        toNumber(summary.portfolio_base_value) > 0
          ? Math.max(toNumber(summary.portfolio_base_value), liveHoldingsValue + currentCash)
          : liveHoldingsValue + currentCash
      const currentAlloc = {
        SMART_CORE: 0,
        TACTICAL: 0,
        SPECULATIVE: 0,
        CASH: totalPortfolioValue > 0 ? (currentCash / totalPortfolioValue) * 100 : 0,
      }
      normalizedHoldings.forEach(holding => {
        const tier = normalizeTier(holding.tier)
        if (tier in currentAlloc) {
          currentAlloc[tier] += totalPortfolioValue > 0 ? (holding.market_value / totalPortfolioValue) * 100 : 0
        }
      })

      return {
        mode: summary.mode,
        totalPortfolioValue,
        cash: currentCash,
        rows: rows.map(row => {
          const holding = holdingBasis.get(row.ticker)
          const currentValue = toNumber(holding?.market_value)
          const currentWeightPct = totalPortfolioValue > 0
            ? Number((((currentValue) / totalPortfolioValue) * 100).toFixed(2))
            : 0
          const targetWeightPct = Number(row.target_weight_pct || 0)
          const targetValue = Number((totalPortfolioValue * (targetWeightPct / 100)).toFixed(2))
          const deltaValue = Number((targetValue - currentValue).toFixed(2))
          const currentlyHeld = toNumber(holding?.shares) > 0 || currentValue > 0
          const recommendation = currentlyHeld && row.recommendation === 'OPEN'
            ? 'ADD'
            : row.recommendation
          return {
            ...row,
            recommendation,
            omnivex_score: row.omnivex_score == null ? null : Number(row.omnivex_score),
            signal_conf: row.signal_conf == null ? null : Number(row.signal_conf),
            current_weight_pct: currentWeightPct,
            target_weight_pct: targetWeightPct,
            current_value: currentValue,
            target_value: targetValue,
            delta_weight_pct: Number((targetWeightPct - currentWeightPct).toFixed(2)),
            delta_value: deltaValue,
            held: currentlyHeld,
            risk: currentlyHeld ? assessHoldingRisk({ ...holding, ...row }, strategyConfig) : null,
          }
        }),
        summary: {
          buyCount: rows.filter(row => row.recommendation === 'ADD').length,
          trimCount: rows.filter(row => row.recommendation === 'TRIM').length,
          exitCount: rows.filter(row => row.recommendation === 'EXIT').length,
          openCount: rows.filter(row => row.recommendation === 'OPEN').length,
          estimatedTurnoverPct: Number(summary.estimated_turnover_pct || 0),
          maxPositions: Number(summary.max_positions || 0),
          notes: summary.notes || '',
          targetCashPct: Number(summary.target_cash_pct || 0),
        },
        targetAlloc: {
          SMART_CORE: Number(summary.target_smart_core_pct || 0),
          TACTICAL: Number(summary.target_tactical_pct || 0),
          SPECULATIVE: Number(summary.target_speculative_pct || 0),
          CASH: Number(summary.target_cash_pct || 0),
        },
        currentAlloc,
      }
    }
  } catch (error) {
    console.warn('Allocator tables unavailable, falling back to legacy rebalance plan:', error.message)
  }

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
      risk: holding ? assessHoldingRisk({ ...holding, ...score }, strategyConfig) : null,
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
      risk: assessHoldingRisk(holding, strategyConfig),
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
      estimatedTurnoverPct: 0,
      maxPositions: 0,
      notes: '',
      targetCashPct: 0,
    },
    targetAlloc: null,
    currentAlloc: null,
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
