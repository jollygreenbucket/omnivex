import {
  getHoldings, getTrades, getPortfolioSnapshots,
  getTierPerformance, getLatestSnapshot, getAllocationSummary,
  getPerformanceVsSpy
} from '../../lib/db'

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end()
  try {
    const [holdings, trades, snapshots, tierPerf, snapshot, allocation, perfVsSpy] =
      await Promise.all([
        getHoldings(),
        getTrades(100),
        getPortfolioSnapshots(90),
        getTierPerformance(90),
        getLatestSnapshot(),
        getAllocationSummary(),
        getPerformanceVsSpy(90),
      ])
    return res.status(200).json({
      holdings, trades, snapshots, tierPerf,
      snapshot, allocation, perfVsSpy,
      generatedAt: new Date().toISOString(),
    })
  } catch (err) {
    console.error('Portfolio API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
