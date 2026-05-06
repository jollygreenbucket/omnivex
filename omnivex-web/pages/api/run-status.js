import { getLatestDailyWorkflowRun } from '../../lib/github'

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  try {
    const run = await getLatestDailyWorkflowRun()
    return res.status(200).json({
      run,
      generatedAt: new Date().toISOString(),
    })
  } catch (err) {
    console.error('Run Status API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
