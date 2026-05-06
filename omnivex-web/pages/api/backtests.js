import { getBacktestRuns, getBacktestDetail } from '../../lib/db'

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { id } = req.query
  try {
    if (id) {
      const detail = await getBacktestDetail(id)
      if (!detail) return res.status(404).json({ error: 'Backtest not found' })
      return res.status(200).json(detail)
    }

    const runs = await getBacktestRuns(20)
    return res.status(200).json({
      runs,
      generatedAt: new Date().toISOString(),
    })
  } catch (err) {
    console.error('Backtests API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
