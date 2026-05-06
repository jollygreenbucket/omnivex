const GITHUB_API_BASE = 'https://api.github.com'
const DEFAULT_WORKFLOW_FILE = 'daily-scorer.yml'
const DEFAULT_BACKTEST_WORKFLOW_FILE = 'backtest.yml'
const DEFAULT_OWNER = 'jollygreenbucket'
const DEFAULT_REPO = 'omnivex'
const DEFAULT_BRANCH = 'main'

function getGithubConfig() {
  const token = process.env.GITHUB_TOKEN
  const owner = process.env.GITHUB_REPO_OWNER || DEFAULT_OWNER
  const repo = process.env.GITHUB_REPO_NAME || DEFAULT_REPO
  const workflowId = process.env.GITHUB_WORKFLOW_ID || DEFAULT_WORKFLOW_FILE
  const branch = process.env.GITHUB_WORKFLOW_REF || DEFAULT_BRANCH

  if (!token) {
    throw new Error(
      'Missing GitHub workflow configuration. Set GITHUB_TOKEN in Vercel project settings.'
    )
  }

  return { token, owner, repo, workflowId, branch }
}

async function githubFetch(path, init = {}) {
  const { token } = getGithubConfig()
  const response = await fetch(`${GITHUB_API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'User-Agent': 'omnivex-dashboard',
      ...(init.headers || {}),
    },
  })

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      message = body.message || message
    } catch {}
    throw new Error(`GitHub API error: ${message}`)
  }

  if (response.status === 204) return null
  return response.json()
}

export async function dispatchDailyWorkflow({ demo = false } = {}) {
  const { owner, repo, workflowId, branch } = getGithubConfig()

  await githubFetch(`/repos/${owner}/${repo}/actions/workflows/${workflowId}/dispatches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: branch,
      inputs: {
        demo: String(Boolean(demo)),
      },
    }),
  })

  return { ok: true }
}

export async function getLatestDailyWorkflowRun() {
  const { owner, repo, workflowId, branch } = getGithubConfig()
  return getLatestWorkflowRun({ owner, repo, workflowId, branch })
}

export async function dispatchBacktestWorkflow({
  startDate = '',
  endDate = '',
  topN = '10',
  weighting = 'equal',
  slippageBps = '10',
} = {}) {
  const { owner, repo, branch } = getGithubConfig()

  await githubFetch(`/repos/${owner}/${repo}/actions/workflows/${DEFAULT_BACKTEST_WORKFLOW_FILE}/dispatches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ref: branch,
      inputs: {
        start_date: String(startDate || ''),
        end_date: String(endDate || ''),
        top_n: String(topN || '10'),
        weighting: String(weighting || 'equal'),
        slippage_bps: String(slippageBps || '10'),
      },
    }),
  })

  return { ok: true }
}

export async function getLatestBacktestWorkflowRun() {
  const { owner, repo, branch } = getGithubConfig()
  return getLatestWorkflowRun({
    owner,
    repo,
    workflowId: DEFAULT_BACKTEST_WORKFLOW_FILE,
    branch,
  })
}

async function getLatestWorkflowRun({ owner, repo, workflowId, branch }) {
  const data = await githubFetch(
    `/repos/${owner}/${repo}/actions/workflows/${workflowId}/runs?per_page=1&branch=${encodeURIComponent(branch)}`
  )

  const run = data?.workflow_runs?.[0]
  if (!run) return null

  return {
    id: run.id,
    name: run.name,
    status: run.status,
    conclusion: run.conclusion,
    htmlUrl: run.html_url,
    runNumber: run.run_number,
    event: run.event,
    headBranch: run.head_branch,
    createdAt: run.created_at,
    updatedAt: run.updated_at,
    actor: run.actor?.login || null,
  }
}
