# OMNIVEX — Paquette Capital
## Trading System Dashboard

---

## Architecture

```
GitHub Repo
├── omnivex/          ← Python scorer (runs via GitHub Actions)
└── omnivex-web/      ← Next.js dashboard (deployed to Vercel)
```

```
GitHub Actions (daily cron @ 4:30 PM EST)
    → run_daily.py
    → writes to Vercel Postgres
    → triggers Vercel redeploy

Vercel
    → serves Next.js dashboard
    → API routes query Vercel Postgres live
    → accessible from anywhere
```

---

## Setup (one-time, ~20 minutes)

### 1. Create Vercel Project

1. Push this repo to GitHub
2. Go to [vercel.com](https://vercel.com) → New Project → Import your repo
3. Set **Root Directory** to `omnivex-web`
4. Deploy

### 2. Create Vercel Postgres Database

1. In your Vercel project → Storage tab → Create Database → Postgres
2. Name it `omnivex-db`
3. Copy the `POSTGRES_URL` connection string

### 3. Run the Database Schema

1. In Vercel → Storage → your database → Query tab
2. Paste contents of `omnivex-web/scripts/schema.sql`
3. Run it

### 4. Add Environment Variables

**In Vercel** (Settings → Environment Variables):
```
POSTGRES_URL = your_connection_string
GITHUB_TOKEN = your_github_token_with_actions_access
GITHUB_REPO_OWNER = jollygreenbucket           # optional override
GITHUB_REPO_NAME = omnivex                     # optional override
GITHUB_WORKFLOW_REF = main                     # optional override
GITHUB_WORKFLOW_ID = daily-scorer.yml          # optional override
```

**In GitHub** (Settings → Secrets → Actions):
```
POSTGRES_URL = your_connection_string (same value)
VERCEL_DEPLOY_HOOK = your_vercel_deploy_hook_url
```

To get your Vercel deploy hook:
Vercel → Project Settings → Git → Deploy Hooks → Create Hook

For `GITHUB_TOKEN`, use a GitHub token that can:
- dispatch Actions workflows
- read workflow run status

If you keep using `jollygreenbucket/omnivex` on `main`, only `GITHUB_TOKEN` is strictly required. The other GitHub env vars are there if you want to point the dashboard at a different repo, branch, or workflow file later.

### 5. Test the Scorer Locally

```bash
cd omnivex
pip install yfinance pandas requests beautifulsoup4 jinja2 colorama psycopg2-binary
export POSTGRES_URL="your_connection_string"
python run_daily.py --demo
```

### 6. Trigger First Full Run

Go to GitHub → Actions → Omnivex Daily Scorer → Run workflow

---

## Daily Operation

The scorer runs automatically at **4:30 PM EST every weekday** via GitHub Actions.

**Manual run:** GitHub → Actions → Omnivex Daily Scorer → Run workflow

**Dashboard-triggered run:** Use the `Run Daily` button in the Vercel header. The dashboard will:
- dispatch `.github/workflows/daily-scorer.yml`
- poll GitHub Actions for status
- refresh the latest Neon-backed data after a successful run

**Dashboard:** Your Vercel URL (e.g. `omnivex.vercel.app`)

---

## Adding Tickers

Edit `omnivex/run_daily.py` → `DEFAULT_UNIVERSE` list.

Or run ad-hoc:
```bash
python run_daily.py --tickers AAPL MSFT NVDA TSLA
```

---

## Modes

| Mode | Meaning | Trigger |
|------|---------|---------|
| Omnivex Alpha | Offense — Tactical-heavy | ≥4 of 6 bullish conditions |
| Omnivex Hedge | Defense — Cash/Inverse ETFs | ≥3 of 5 bearish conditions |
| Omnivex Core | Holding pattern | Neither threshold met |

---

## Score Interpretation

| Score | Action |
|-------|--------|
| 80–100 | BREAKOUT — buy/add |
| 70–79 | OVERWEIGHT |
| 60–69 | MAINTAIN |
| 50–59 | UNDERWEIGHT — reduce |
| <50 | EXCLUDE — remove |

---

*Omnivex v1.0 — Paquette Capital*
