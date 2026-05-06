import { dispatchDailyWorkflow, getLatestDailyWorkflowRun } from '../../lib/github'

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  try {
    const demo = req.body?.demo === true
    await dispatchDailyWorkflow({ demo })

    // The dispatch endpoint is async; best-effort fetch the newest visible run after a short delay.
    await new Promise(resolve => setTimeout(resolve, 1500))
    const run = await getLatestDailyWorkflowRun()

    return res.status(202).json({
      ok: true,
      message: 'Daily scorer triggered',
      run,
    })
  } catch (err) {
    console.error('Run Daily API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
