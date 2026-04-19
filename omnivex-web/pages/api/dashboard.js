import {
  getLatestRun, getLatestScores, getModeHistory,
  getTopMovers, getScoreDistribution, getRunHistory
} from '../../lib/db'

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  try {
    const [run, scores, modeHistory, movers, distribution, runHistory] =
      await Promise.all([
        getLatestRun(),
        getLatestScores(),
        getModeHistory(90),
        getTopMovers(10),
        getScoreDistribution(),
        getRunHistory(30),
      ])

    return res.status(200).json({
      run,
      scores,
      modeHistory,
      movers,
      distribution,
      runHistory,
      generatedAt: new Date().toISOString(),
    })
  } catch (err) {
    console.error('Dashboard API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
