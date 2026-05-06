import { dispatchBacktestWorkflow, getLatestBacktestWorkflowRun } from '../../lib/github'

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const {
    startDate = '',
    endDate = '',
    topN = '10',
    weighting = 'equal',
    slippageBps = '10',
  } = req.body || {}

  try {
    await dispatchBacktestWorkflow({ startDate, endDate, topN, weighting, slippageBps })
    await new Promise(resolve => setTimeout(resolve, 1500))
    const run = await getLatestBacktestWorkflowRun()

    return res.status(202).json({
      ok: true,
      message: 'Backtest workflow triggered',
      run,
    })
  } catch (err) {
    console.error('Run Backtest API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
