import { getRunDetail } from '../../lib/db'

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { date } = req.query
  if (!date) {
    return res.status(400).json({ error: 'date required' })
  }

  try {
    const detail = await getRunDetail(date)
    if (!detail) {
      return res.status(404).json({ error: 'Run not found' })
    }
    return res.status(200).json(detail)
  } catch (err) {
    console.error('Run detail API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
