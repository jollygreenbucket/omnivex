import {
  getHoldings, getTrades, getPortfolioSnapshots,
  getTierPerformance, getLatestSnapshot, getAllocationSummary,
  getPerformanceVsSpy, getRebalancePlan, getPortfolioTransactions, upsertHolding
} from '../../lib/db'

export default async function handler(req, res) {
  try {
    if (req.method === 'POST') {
      const holding = await upsertHolding(req.body || {})
      return res.status(200).json({ holding })
    }

    if (req.method !== 'GET') return res.status(405).end()

    const [holdings, trades, transactions, snapshots, tierPerf, snapshot, allocation, perfVsSpy, rebalance] =
      await Promise.all([
        getHoldings(),
        getTrades(100),
        getPortfolioTransactions(100),
        getPortfolioSnapshots(90),
        getTierPerformance(90),
        getLatestSnapshot(),
        getAllocationSummary(),
        getPerformanceVsSpy(90),
        getRebalancePlan(),
      ])
    return res.status(200).json({
      holdings, trades, transactions, snapshots, tierPerf,
      snapshot, allocation, perfVsSpy, rebalance,
      generatedAt: new Date().toISOString(),
    })
  } catch (err) {
    console.error('Portfolio API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
