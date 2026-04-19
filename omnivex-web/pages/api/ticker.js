import { getTickerHistory, getLatestScores } from '../../lib/db'

export default async function handler(req, res) {
  const { ticker } = req.query
  if (!ticker) return res.status(400).json({ error: 'ticker required' })

  try {
    const [history, latest] = await Promise.all([
      getTickerHistory(ticker.toUpperCase(), 60),
      getLatestScores(),
    ])
    const current = latest.find(s => s.ticker === ticker.toUpperCase()) || null
    return res.status(200).json({ ticker: ticker.toUpperCase(), history, current })
  } catch (err) {
    return res.status(500).json({ error: err.message })
  }
}
