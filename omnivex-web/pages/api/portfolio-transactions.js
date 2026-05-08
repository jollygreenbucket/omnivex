import { getPortfolioTransactions, insertPortfolioTransaction } from '../../lib/db'

export default async function handler(req, res) {
  try {
    if (req.method === 'POST') {
      const result = await insertPortfolioTransaction(req.body || {})
      return res.status(200).json(result)
    }

    if (req.method !== 'GET') return res.status(405).end()

    const transactions = await getPortfolioTransactions(100)
    return res.status(200).json({ transactions })
  } catch (err) {
    console.error('Portfolio transactions API error:', err)
    return res.status(500).json({ error: err.message })
  }
}
