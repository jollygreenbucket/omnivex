# Omnivex
### Paquette Capital — Private Trading System

---

Omnivex is a private algorithmic trading system built for systematic signal generation, mode-switching portfolio management, and live execution via the Schwab API.

---

## Repository Structure

```
paquette-capital/
├── omnivex/              Python scoring engine
│   ├── core/             Scoring, mode detection, configuration
│   ├── data/             Data ingestion (yfinance, Finviz) + DB writer
│   ├── output/           Terminal, CSV, and HTML report generation
│   ├── logs/             Daily audit CSVs (gitignored)
│   ├── reports/          Daily HTML reports (gitignored)
│   └── run_daily.py      Main entry point
│
├── omnivex-web/          Next.js dashboard
│   ├── pages/            Routes and API endpoints
│   ├── lib/              Vercel Postgres query layer
│   ├── styles/           Global CSS design system
│   ├── scripts/          Database schema SQL
│   └── components/       Shared UI components
│
└── .github/
    └── workflows/
        └── daily-scorer.yml   GitHub Actions cron job
```

---

## System Overview

**Omnivex Score** = `0.4 × QTech + 0.3 × PSOS + 0.3 × Signal Confidence`

| Score | Interpretation |
|-------|---------------|
| 80–100 | Breakout |
| 70–79 | Overweight |
| 60–69 | Maintain |
| 50–59 | Underweight |
| <50 | Exclude |

**Operating Modes**

| Mode | Trigger | Posture |
|------|---------|---------|
| Omnivex Alpha | ≥4 of 6 bullish conditions | Tactical-heavy offense |
| Omnivex Hedge | ≥3 of 5 bearish conditions | Cash/inverse ETF defense |
| Omnivex Core | Neither threshold met | Balanced, capital-preserving |

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Vercel account with Postgres database
- Schwab Developer API credentials (for live execution)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/paquette-capital.git
cd paquette-capital

# Python dependencies
cd omnivex
pip install yfinance pandas requests beautifulsoup4 jinja2 colorama psycopg2-binary

# Node dependencies
cd ../omnivex-web
npm install
```

### 2. Environment variables

Create `omnivex/.env`:
```
POSTGRES_URL=your_vercel_postgres_connection_string
```

Create `omnivex-web/.env.local`:
```
POSTGRES_URL=your_vercel_postgres_connection_string
```

### 3. Database setup

In your Vercel Postgres console, run:
1. `omnivex-web/scripts/schema.sql`
2. `omnivex-web/scripts/schema_portfolio.sql`

### 4. Run locally

```bash
# Scorer (paper mode)
cd omnivex
python run_daily.py --demo

# Dashboard
cd omnivex-web
npm run dev
# → http://localhost:3000
```

### 5. Deploy to Vercel

```bash
cd omnivex-web
vercel --prod
```

---

## GitHub Actions — Automated Daily Runs

The scorer runs automatically at **4:30 PM EST every weekday**.

Required GitHub secrets:
```
POSTGRES_URL          Vercel Postgres connection string
VERCEL_DEPLOY_HOOK    Vercel deploy hook URL (triggers dashboard refresh)
```

Manual trigger: GitHub → Actions → Omnivex Daily Scorer → Run workflow

---

## Schwab API Integration

Register at [developer.schwab.com](https://developer.schwab.com).

Execution staging:
- **Stage 1** — Recommendations only (current default)
- **Stage 2** — Human-approved blotter (target for live)
- **Stage 3** — Semi-automated for liquid names
- **Stage 4** — Full automation (after audit history validates stability)

---

## Data Sources

| Source | Usage |
|--------|-------|
| yfinance | Price, fundamentals, RSI, moving averages |
| Finviz | Top gainers, high volume, insider activity |
| Schwab API | Order execution (Stage 2+) |
| Vercel Postgres | Persistent storage, calibration history |

---

*Private repository — Paquette Capital. All rights reserved.*
