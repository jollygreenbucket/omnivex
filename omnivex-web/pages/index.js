import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, ReferenceLine
} from 'recharts'

// ─── Utilities ─────────────────────────────────────────────────────────────

const fmt  = (n, d = 1) => n == null || isNaN(n) ? '—' : Number(n).toFixed(d)
const fmtM = (n) => n == null ? '—' : `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const fmtPct = (n) => n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n * 100, 2)}%`
const fmtDate = (d) => !d ? '—' : new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
const fmtDateFull = (d) => !d ? '—' : new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

function scoreCol(s) {
  if (s >= 80) return '#2dd4a0'
  if (s >= 70) return '#6eb3f7'
  if (s >= 60) return '#d4a03a'
  if (s >= 50) return '#e07c3a'
  return '#e05252'
}
function scoreCls(s) {
  if (s >= 80) return 'c-breakout'
  if (s >= 70) return 'c-overweight'
  if (s >= 60) return 'c-maintain'
  if (s >= 50) return 'c-underweight'
  return 'c-exclude'
}
function modeCls(m) {
  if (!m) return 'badge-core'
  m = m.toUpperCase()
  if (m === 'ALPHA') return 'badge-alpha'
  if (m === 'HEDGE') return 'badge-hedge'
  return 'badge-core'
}
function modeLabel(m) {
  if (!m) return 'Core'
  if (m === 'ALPHA') return 'Omnivex Alpha'
  if (m === 'HEDGE') return 'Omnivex Hedge'
  return 'Omnivex Core'
}
function modeAccentColor(m) {
  if (m === 'ALPHA') return '#2dd4a0'
  if (m === 'HEDGE') return '#e05252'
  return '#d4a03a'
}
function tierLabel(t) {
  if (!t) return 'Monitor'
  return t.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
}
function tierCol(t) {
  if (!t) return '#363d52'
  if (t.includes('SMART')) return '#6eb3f7'
  if (t.includes('TACTICAL')) return '#a78bfa'
  if (t.includes('SPEC')) return '#d4a03a'
  return '#363d52'
}

// ─── Shared Components ─────────────────────────────────────────────────────

function ChartTip({ active, payload, label, prefix = '' }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0e1018', border: '1px solid #1c2130',
      borderRadius: 6, padding: '10px 14px', fontSize: 11,
      fontFamily: 'var(--font-mono)',
    }}>
      <div style={{ color: '#5a6278', marginBottom: 6, fontSize: 10 }}>{fmtDate(label)}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, marginBottom: 2 }}>
          {p.name}: {prefix}{typeof p.value === 'number' ? fmt(p.value, 2) : p.value}
        </div>
      ))}
    </div>
  )
}

function StatCard({ label, value, sub, accent, className = 'anim-1' }) {
  return (
    <div className={`card card-sm ${className}`} style={{
      borderTop: accent ? `2px solid ${accent}` : '2px solid transparent',
    }}>
      <div className="label" style={{ marginBottom: 10 }}>{label}</div>
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 26,
        fontWeight: 400, color: accent || 'var(--text)',
        lineHeight: 1.1,
      }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--silver-2)', marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

function ScoreBar({ value }) {
  return (
    <div className="score-bar" style={{ width: 52 }}>
      <div className="score-bar-fill" style={{
        width: `${Math.min(100, value || 0)}%`,
        background: scoreCol(value),
      }} />
    </div>
  )
}

function SectionLabel({ children }) {
  return <div className="divider-label">{children}</div>
}

// ─── Main App ──────────────────────────────────────────────────────────────

export default function Omnivex() {
  const [tab, setTab] = useState('signals')
  const [dashData, setDashData] = useState(null)
  const [portData, setPortData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [tierF, setTierF] = useState('ALL')
  const [actionF, setActionF] = useState('ALL')
  const [sortCol, setSortCol] = useState('omnivex_score')
  const [focusTicker, setFocusTicker] = useState(null)
  const [tickerHist, setTickerHist] = useState(null)

  // Fetch dashboard data
  useEffect(() => {
    Promise.all([
      fetch('/api/dashboard').then(r => r.json()),
      fetch('/api/portfolio').then(r => r.json()).catch(() => null),
    ]).then(([d, p]) => {
      setDashData(d)
      setPortData(p)
      setLoading(false)
    })
  }, [])

  // Fetch ticker history on focus
  useEffect(() => {
    if (!focusTicker) return
    setTickerHist(null)
    fetch(`/api/ticker?ticker=${focusTicker}`)
      .then(r => r.json()).then(setTickerHist)
  }, [focusTicker])

  const scores = useMemo(() => {
    if (!dashData?.scores) return []
    return dashData.scores
      .filter(s => {
        const ms = !search || s.ticker.includes(search.toUpperCase()) ||
          (s.sector || '').toLowerCase().includes(search.toLowerCase())
        const mt = tierF === 'ALL' || s.tier === tierF
        const ma = actionF === 'ALL' || s.action === actionF
        return ms && mt && ma
      })
      .sort((a, b) => (b[sortCol] || 0) - (a[sortCol] || 0))
  }, [dashData, search, tierF, actionF, sortCol])

  // ── Loading ──
  if (loading) return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 24,
    }}>
      <div style={{
        fontFamily: 'var(--font-serif)', fontSize: 42,
        color: 'var(--gold)', letterSpacing: '.06em', fontStyle: 'italic',
      }}>Omnivex</div>
      <div style={{ width: 48, height: 1, background: 'var(--gold)', opacity: .4 }} />
      <div className="label">Paquette Capital</div>
    </div>
  )

  // ── No data ──
  if (!dashData?.run) return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 16,
    }}>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--gold)' }}>
        Awaiting First Run
      </div>
      <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>
        No data found. Run the scorer to populate.
      </div>
      <code style={{
        fontFamily: 'var(--font-mono)', fontSize: 11,
        background: 'var(--ink-2)', padding: '6px 14px',
        borderRadius: 4, color: 'var(--silver)',
      }}>python run_daily.py</code>
    </div>
  )

  const { run, modeHistory, movers, distribution, runHistory } = dashData
  const mode = run?.mode || 'CORE'
  const accent = modeAccentColor(mode)

  const holdings = portData?.holdings || []
  const trades = portData?.trades || []
  const snapshots = portData?.snapshots || []
  const allocation = portData?.allocation || []
  const perfVsSpy = portData?.perfVsSpy || []
  const snap = portData?.snapshot

  // Compute portfolio totals
  const totalValue = holdings.reduce((s, h) => s + (h.market_value || 0), 0)
  const totalPnl = holdings.reduce((s, h) => s + (h.unrealized_pnl || 0), 0)
  const totalCost = totalValue - totalPnl
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0

  // Cumulative performance chart
  const perfChart = useMemo(() => {
    let cumPort = 0, cumSpy = 0
    return perfVsSpy.map(d => {
      cumPort += (d.total_pnl_pct || 0) * 100
      cumSpy += (d.spy_daily_pct || 0) * 100
      return {
        date: d.snapshot_date,
        portfolio: +cumPort.toFixed(2),
        spy: +cumSpy.toFixed(2),
        mode: d.mode,
      }
    })
  }, [perfVsSpy])

  // Target allocation by mode
  const targetAlloc = {
    ALPHA:  { SMART_CORE: 35, TACTICAL: 45, SPECULATIVE: 15, CASH: 5 },
    HEDGE:  { SMART_CORE: 15, TACTICAL: 5,  SPECULATIVE: 0,  CASH: 80 },
    CORE:   { SMART_CORE: 52, TACTICAL: 25, SPECULATIVE: 7,  CASH: 16 },
  }[mode] || {}

  const actualAlloc = {}
  allocation.forEach(a => {
    actualAlloc[a.tier] = totalValue > 0
      ? +((a.total_value / totalValue) * 100).toFixed(1)
      : 0
  })

  return (
    <>
      <Head>
        <title>Omnivex — Paquette Capital</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* ══ HEADER ══ */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(8,9,13,.92)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--ink-4)',
        padding: '0 36px',
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', height: 58,
      }}>
        {/* Wordmark */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 18 }}>
          <span style={{
            fontFamily: 'var(--font-serif)', fontSize: 21,
            color: 'var(--gold)', letterSpacing: '.04em', fontStyle: 'italic',
          }}>Omnivex</span>
          <span className="label" style={{ letterSpacing: '.2em', opacity: .5 }}>
            Paquette Capital
          </span>
        </div>

        {/* Center nav */}
        <nav style={{ display: 'flex', gap: 0, borderBottom: 'none' }}>
          {[
            ['signals', 'Signals'],
            ['portfolio', 'Portfolio'],
            ['history', 'History'],
          ].map(([id, lbl]) => (
            <button key={id} className={`nav-tab ${tab === id ? 'active' : ''}`}
              onClick={() => setTab(id)}>
              {lbl}
            </button>
          ))}
        </nav>

        {/* Right status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span className={`badge ${modeCls(mode)}`}>{modeLabel(mode)}</span>
          {run?.chop_guard && (
            <span className="badge badge-gold">Chop Guard</span>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <span className="live-pip" />
            <span className="label">{fmtDate(run?.run_date)}</span>
          </div>
        </div>
      </header>

      <main style={{ padding: '32px 36px', maxWidth: 1440, margin: '0 auto' }}>

        {/* ══ SIGNALS TAB ══ */}
        {tab === 'signals' && (
          <div>
            {/* Market stat row */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(8, 1fr)',
              gap: 10, marginBottom: 28,
            }}>
              {[
                ['Mode', modeLabel(mode), null, accent, 'anim-1'],
                ['VIX', fmt(run?.vix), null, run?.vix < 18 ? '#2dd4a0' : run?.vix > 22 ? '#e05252' : '#d4a03a', 'anim-1'],
                ['SPY', `${(run?.spy_daily_pct||0)>=0?'+':''}${fmt(run?.spy_daily_pct)}%`, null,
                  (run?.spy_daily_pct||0)>=0?'#2dd4a0':'#e05252', 'anim-2'],
                ['A/D', fmt(run?.ad_ratio,2), null, null, 'anim-2'],
                ['Yield Curve', run?.yield_curve_state||'—', null, run?.yield_curve_state==='INVERTED'?'#e05252':'#2dd4a0', 'anim-3'],
                ['Tickers', run?.tickers_scored, `${run?.tickers_buy||0} buy · ${run?.tickers_reduce||0} reduce`, null, 'anim-3'],
                ['Alpha', `${run?.alpha_trigger_count||0}/6`, null, run?.alpha_trigger_count>=4?'#2dd4a0':null, 'anim-4'],
                ['Hedge', `${run?.hedge_trigger_count||0}/5`, null, run?.hedge_trigger_count>=3?'#e05252':null, 'anim-4'],
              ].map(([label, value, sub, ac, cls]) => (
                <StatCard key={label} label={label} value={value}
                  sub={sub} accent={ac} className={cls} />
              ))}
            </div>

            {/* Top picks row */}
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
              gap: 14, marginBottom: 28,
            }}>
              {/* Buys */}
              <div className="card anim-2" style={{ borderTop: '2px solid var(--alpha)' }}>
                <div className="label" style={{ color: 'var(--alpha)', marginBottom: 16 }}>
                  Top Buy Candidates
                </div>
                {scores.filter(s => ['BUY','ADD'].includes(s.action)).slice(0, 6).map(s => (
                  <div key={s.ticker} onClick={() => setFocusTicker(s.ticker)}
                    style={{
                      display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', padding: '9px 0',
                      borderBottom: '1px solid var(--ink-2)', cursor: 'pointer',
                    }}>
                    <div>
                      <span style={{ fontWeight: 400, fontSize: 13 }}>{s.ticker}</span>
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 9,
                        color: tierCol(s.tier), marginLeft: 8,
                      }}>{tierLabel(s.tier)}</span>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div className={`${scoreCls(s.omnivex_score)} mono`} style={{ fontSize: 13 }}>
                        {fmt(s.omnivex_score)}
                      </div>
                      <ScoreBar value={s.omnivex_score} />
                    </div>
                  </div>
                ))}
                {scores.filter(s=>['BUY','ADD'].includes(s.action)).length === 0 && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>
                    None at current thresholds
                  </div>
                )}
              </div>

              {/* Reduce/Remove */}
              <div className="card anim-2" style={{ borderTop: '2px solid var(--hedge)' }}>
                <div className="label" style={{ color: 'var(--hedge)', marginBottom: 16 }}>
                  Reduce / Rotate
                </div>
                {scores.filter(s=>['REDUCE','REMOVE','ROTATE'].includes(s.action)).slice(0,6).map(s => (
                  <div key={s.ticker} onClick={() => setFocusTicker(s.ticker)}
                    style={{
                      display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', padding: '9px 0',
                      borderBottom: '1px solid var(--ink-2)', cursor: 'pointer',
                    }}>
                    <span style={{ fontSize: 13 }}>{s.ticker}</span>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <span className={`c-${(s.action||'').toLowerCase()} mono`} style={{ fontSize: 10 }}>
                        {s.action}
                      </span>
                      <span className={`${scoreCls(s.omnivex_score)} mono`} style={{ fontSize: 13 }}>
                        {fmt(s.omnivex_score)}
                      </span>
                    </div>
                  </div>
                ))}
                {scores.filter(s=>['REDUCE','REMOVE','ROTATE'].includes(s.action)).length===0 && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>None flagged</div>
                )}
              </div>

              {/* Forensic + Mode shift */}
              <div className="card anim-2">
                <div className="label" style={{ color: 'var(--gold)', marginBottom: 16 }}>
                  System Alerts
                </div>
                {/* Mode shift watch */}
                <div style={{
                  background: 'var(--ink-2)', borderRadius: 6,
                  padding: '10px 14px', marginBottom: 12,
                }}>
                  <div className="label" style={{ marginBottom: 6 }}>Mode Proximity</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {[
                      ['Alpha', run?.alpha_trigger_count||0, 6, 'var(--alpha)'],
                      ['Hedge', run?.hedge_trigger_count||0, 5, 'var(--hedge)'],
                    ].map(([name, count, total, color]) => (
                      <div key={name}>
                        <div style={{
                          display: 'flex', justifyContent: 'space-between',
                          marginBottom: 4,
                        }}>
                          <span style={{ fontSize: 11, color }}>{name}</span>
                          <span className="mono" style={{ fontSize: 10, color: 'var(--silver-2)' }}>
                            {count}/{total}
                          </span>
                        </div>
                        <div style={{ height: 2, background: 'var(--ink-4)', borderRadius: 1 }}>
                          <div style={{
                            height: '100%', borderRadius: 1, background: color,
                            width: `${(count/total)*100}%`,
                          }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Forensic flags */}
                {scores.filter(s=>s.forensic_flag).length > 0 && (
                  <>
                    <div className="label" style={{ color: 'var(--hedge)', marginBottom: 8 }}>
                      ⚠ Forensic Flags
                    </div>
                    {scores.filter(s=>s.forensic_flag).map(s => (
                      <div key={s.ticker} style={{
                        padding: '7px 0', borderBottom: '1px solid var(--ink-2)',
                      }}>
                        <div style={{ fontWeight: 400, marginBottom: 2 }}>{s.ticker}</div>
                        <div style={{ fontSize: 10, color: 'var(--silver-2)' }}>
                          {(s.forensic_detail||'').replace(/\|/g,' · ')}
                        </div>
                      </div>
                    ))}
                  </>
                )}
                {scores.filter(s=>s.forensic_flag).length===0 && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>No forensic flags</div>
                )}
              </div>
            </div>

            {/* Score distribution */}
            {distribution?.length > 0 && (
              <div className="card anim-3" style={{ marginBottom: 28 }}>
                <div className="label" style={{ marginBottom: 16 }}>Score Distribution</div>
                <ResponsiveContainer width="100%" height={72}>
                  <BarChart data={distribution} barSize={40} barGap={4}>
                    <XAxis dataKey="band" tick={{ fill: '#5a6278', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                      axisLine={false} tickLine={false} />
                    <YAxis hide />
                    <Tooltip contentStyle={{
                      background: '#0e1018', border: '1px solid #1c2130',
                      borderRadius: 6, fontSize: 11, fontFamily: 'var(--font-mono)',
                    }} />
                    <Bar dataKey="count" radius={[3,3,0,0]}>
                      {distribution.map((d,i) => (
                        <Cell key={i} fill={scoreCol(
                          d.band==='Breakout'?85:d.band==='Overweight'?75:
                          d.band==='Maintain'?65:d.band==='Underweight'?55:40
                        )} fillOpacity={.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Full table */}
            <div className="card anim-4" style={{ padding: 0, overflow: 'hidden' }}>
              {/* Controls */}
              <div style={{
                padding: '14px 20px', borderBottom: '1px solid var(--ink-3)',
                display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
              }}>
                <input className="pq-input" value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search ticker / sector..." style={{ width: 200 }} />
                <div style={{ display: 'flex', gap: 6 }}>
                  {['ALL','SMART_CORE','TACTICAL','SPECULATIVE'].map(t => (
                    <button key={t} className={`filter-pill ${tierF===t?'active':''}`}
                      onClick={() => setTierF(t)}>
                      {t.replace('_',' ')}
                    </button>
                  ))}
                </div>
                <select className="pq-input" value={actionF}
                  onChange={e => setActionF(e.target.value)} style={{ width: 110 }}>
                  {['ALL','BUY','ADD','HOLD','REDUCE','REMOVE','ROTATE','MONITOR'].map(a => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
                <span className="label" style={{ marginLeft: 'auto' }}>
                  {scores.length} results
                </span>
              </div>

              {/* Table */}
              <div style={{ overflowX: 'auto' }}>
                <table className="pq-table">
                  <thead>
                    <tr>
                      {[
                        ['ticker','Ticker'],['sector','Sector'],['tier','Tier'],
                        ['omnivex_score','Score'],['qtech','QTech'],
                        ['psos','PSOS'],['signal_conf','Sig. Conf'],
                        ['action','Action'],['suggested_weight_pct','Weight'],
                      ].map(([key, lbl]) => (
                        <th key={key} onClick={() => setSortCol(key)}
                          style={{ cursor: 'pointer', userSelect: 'none' }}>
                          {lbl}{sortCol===key?' ↓':''}
                        </th>
                      ))}
                      <th>Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map(s => (
                      <tr key={s.ticker} onClick={() => setFocusTicker(s.ticker)}>
                        <td style={{ fontWeight: 400, letterSpacing: '.02em' }}>{s.ticker}</td>
                        <td style={{ color: 'var(--silver-2)' }}>{s.sector||'—'}</td>
                        <td>
                          <span style={{
                            fontFamily: 'var(--font-mono)', fontSize: 9,
                            color: tierCol(s.tier),
                          }}>
                            {tierLabel(s.tier)}
                          </span>
                        </td>
                        <td>
                          <div>
                            <span className={`${scoreCls(s.omnivex_score)} mono`} style={{ fontSize: 13 }}>
                              {fmt(s.omnivex_score)}
                            </span>
                            <ScoreBar value={s.omnivex_score} />
                          </div>
                        </td>
                        <td className="mono" style={{ color: 'var(--silver-2)' }}>{fmt(s.qtech)}</td>
                        <td className="mono" style={{ color: 'var(--silver-2)' }}>{fmt(s.psos)}</td>
                        <td className="mono" style={{ color: 'var(--silver-2)' }}>{fmt(s.signal_conf)}</td>
                        <td className={`c-${(s.action||'monitor').toLowerCase()} mono`} style={{ fontSize: 11 }}>
                          {s.action||'—'}
                        </td>
                        <td className="mono" style={{ color: 'var(--silver-2)' }}>
                          {s.suggested_weight_pct ? `${fmt(s.suggested_weight_pct)}%` : '—'}
                        </td>
                        <td>
                          {s.forensic_flag && <span className="badge badge-hedge" style={{ marginRight: 4 }}>Forensic</span>}
                          {(s.flags||'').includes('EARNINGS_IMMINENT') && (
                            <span className="badge badge-gold">Earnings</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ══ PORTFOLIO TAB ══ */}
        {tab === 'portfolio' && (
          <div>
            {holdings.length === 0 ? (
              <div className="card" style={{ textAlign: 'center', padding: 60 }}>
                <div style={{
                  fontFamily: 'var(--font-serif)', fontSize: 22,
                  color: 'var(--gold)', marginBottom: 12,
                }}>No Holdings</div>
                <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>
                  Add holdings via the Schwab sync or directly in Vercel Postgres.
                </div>
                <code className="mono" style={{
                  display: 'block', marginTop: 16, fontSize: 11,
                  background: 'var(--ink-2)', padding: '8px 16px',
                  borderRadius: 4, color: 'var(--silver)',
                }}>INSERT INTO holdings (ticker, shares, avg_cost, tier, date_entered) VALUES (...)</code>
              </div>
            ) : (
              <>
                {/* Portfolio summary */}
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(5,1fr)',
                  gap: 10, marginBottom: 28,
                }}>
                  <StatCard label="Total Value" value={fmtM(totalValue)} accent="var(--gold)" />
                  <StatCard label="Unrealized P&L"
                    value={fmtM(totalPnl)}
                    sub={`${totalPnlPct >= 0 ? '+' : ''}${fmt(totalPnlPct)}%`}
                    accent={totalPnl >= 0 ? 'var(--alpha)' : 'var(--hedge)'} />
                  <StatCard label="Positions" value={holdings.length} />
                  <StatCard label="Cash"
                    value={fmtM(snap?.cash)}
                    sub={snap?.cash && totalValue ? `${fmt((snap.cash/totalValue)*100)}% of portfolio` : null} />
                  <StatCard label="Mode" value={modeLabel(mode)} accent={accent} />
                </div>

                {/* Performance vs SPY */}
                {perfChart.length > 0 && (
                  <div className="card" style={{ marginBottom: 20 }}>
                    <div className="label" style={{ marginBottom: 16 }}>
                      Performance vs SPY — Cumulative %
                    </div>
                    <ResponsiveContainer width="100%" height={180}>
                      <LineChart data={perfChart}>
                        <defs>
                          <linearGradient id="portGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={accent} stopOpacity={.2} />
                            <stop offset="95%" stopColor={accent} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <XAxis dataKey="date" tickFormatter={fmtDate}
                          tick={{ fill: '#5a6278', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                          axisLine={false} tickLine={false} interval="preserveStartEnd" />
                        <YAxis tick={{ fill: '#5a6278', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                          axisLine={false} tickLine={false} width={36}
                          tickFormatter={v => `${v>0?'+':''}${v.toFixed(1)}%`} />
                        <Tooltip content={<ChartTip prefix="" />} />
                        <ReferenceLine y={0} stroke="#1c2130" strokeDasharray="4 4" />
                        <Line type="monotone" dataKey="portfolio" name="Omnivex"
                          stroke={accent} strokeWidth={2} dot={false} />
                        <Line type="monotone" dataKey="spy" name="SPY"
                          stroke="#363d52" strokeWidth={1.5}
                          strokeDasharray="4 4" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Allocation: target vs actual */}
                <div style={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr',
                  gap: 14, marginBottom: 20,
                }}>
                  <div className="card">
                    <div className="label" style={{ marginBottom: 16 }}>
                      Allocation — Target vs Actual
                    </div>
                    {['SMART_CORE','TACTICAL','SPECULATIVE','CASH'].map(tier => {
                      const target = targetAlloc[tier] || 0
                      const actual = actualAlloc[tier] || 0
                      const col = tierCol(tier)
                      return (
                        <div key={tier} style={{ marginBottom: 16 }}>
                          <div style={{
                            display: 'flex', justifyContent: 'space-between', marginBottom: 6,
                          }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: col }}>
                              {tierLabel(tier)}
                            </span>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--silver-2)' }}>
                              <span style={{ color: 'var(--text)' }}>{fmt(actual)}%</span>
                              &nbsp;/&nbsp;{fmt(target)}% target
                            </div>
                          </div>
                          {/* Target bar */}
                          <div style={{ height: 3, background: 'var(--ink-3)', borderRadius: 2, marginBottom: 3 }}>
                            <div style={{
                              height: '100%', width: `${target}%`,
                              background: col, opacity: .3, borderRadius: 2,
                            }} />
                          </div>
                          {/* Actual bar */}
                          <div style={{ height: 3, background: 'var(--ink-3)', borderRadius: 2 }}>
                            <div style={{
                              height: '100%',
                              width: `${Math.min(100, actual)}%`,
                              background: actual > target + 5 ? 'var(--hedge)' :
                                          actual < target - 5 ? 'var(--core)' : col,
                              borderRadius: 2,
                            }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Tier P&L summary */}
                  <div className="card">
                    <div className="label" style={{ marginBottom: 16 }}>
                      Tier Performance
                    </div>
                    <table className="pq-table" style={{ width: '100%' }}>
                      <thead>
                        <tr>
                          <th>Tier</th><th>Positions</th>
                          <th>Value</th><th>P&L</th><th>Avg Score</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allocation.map(a => (
                          <tr key={a.tier}>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: tierCol(a.tier) }}>
                              {tierLabel(a.tier)}
                            </td>
                            <td className="mono">{a.positions}</td>
                            <td className="mono">{fmtM(a.total_value)}</td>
                            <td className={`mono ${a.total_pnl >= 0 ? 'c-pos' : 'c-neg'}`}>
                              {fmtM(a.total_pnl)}
                            </td>
                            <td className={`mono ${scoreCls(a.avg_score)}`}>
                              {fmt(a.avg_score)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Holdings table */}
                <SectionLabel>Current Holdings</SectionLabel>
                <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 20 }}>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="pq-table">
                      <thead>
                        <tr>
                          <th>Ticker</th><th>Tier</th><th>Shares</th>
                          <th>Avg Cost</th><th>Price</th><th>Value</th>
                          <th>P&L</th><th>P&L %</th>
                          <th>Score</th><th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {holdings.map(h => (
                          <tr key={h.ticker} onClick={() => setFocusTicker(h.ticker)}>
                            <td style={{ fontWeight: 400 }}>{h.ticker}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: tierCol(h.tier) }}>
                              {tierLabel(h.tier)}
                            </td>
                            <td className="mono">{fmt(h.shares, 2)}</td>
                            <td className="mono">${fmt(h.avg_cost, 2)}</td>
                            <td className="mono">${fmt(h.current_price, 2)}</td>
                            <td className="mono">{fmtM(h.market_value)}</td>
                            <td className={`mono ${(h.unrealized_pnl||0)>=0?'c-pos':'c-neg'}`}>
                              {fmtM(h.unrealized_pnl)}
                            </td>
                            <td className={`mono ${(h.unrealized_pnl_pct||0)>=0?'c-pos':'c-neg'}`}>
                              {fmtPct(h.unrealized_pnl_pct)}
                            </td>
                            <td className={`mono ${scoreCls(h.omnivex_score)}`}>
                              {fmt(h.omnivex_score)}
                            </td>
                            <td className={`c-${(h.action||'monitor').toLowerCase()} mono`} style={{ fontSize: 10 }}>
                              {h.action||'—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Trade blotter */}
                <SectionLabel>Trade Blotter</SectionLabel>
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="pq-table">
                      <thead>
                        <tr>
                          <th>Date</th><th>Ticker</th><th>Action</th>
                          <th>Shares</th><th>Price</th><th>Total</th>
                          <th>Score at Trade</th><th>Tier</th><th>Mode</th><th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map(t => (
                          <tr key={t.id}>
                            <td className="mono" style={{ color: 'var(--silver-2)' }}>
                              {fmtDate(t.trade_date)}
                            </td>
                            <td style={{ fontWeight: 400 }}>{t.ticker}</td>
                            <td className={`c-${(t.action||'').toLowerCase()} mono`} style={{ fontSize: 10 }}>
                              {t.action}
                            </td>
                            <td className="mono">{fmt(t.shares, 4)}</td>
                            <td className="mono">${fmt(t.price, 2)}</td>
                            <td className="mono">{fmtM(t.total_value)}</td>
                            <td className={`mono ${scoreCls(t.omnivex_score)}`}>{fmt(t.omnivex_score)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: tierCol(t.tier) }}>
                              {tierLabel(t.tier)}
                            </td>
                            <td><span className={`badge ${modeCls(t.mode)}`}>{modeLabel(t.mode)}</span></td>
                            <td style={{ color: 'var(--silver-2)' }}>{t.notes||'—'}</td>
                          </tr>
                        ))}
                        {trades.length === 0 && (
                          <tr><td colSpan={10} style={{ color: 'var(--silver-2)', textAlign: 'center', padding: 32 }}>
                            No trades logged yet
                          </td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ══ HISTORY TAB ══ */}
        {tab === 'history' && (
          <div>
            {/* VIX + A/D chart */}
            <div className="card anim-1" style={{ marginBottom: 20 }}>
              <div className="label" style={{ marginBottom: 16 }}>
                Market Context — 90 Days
              </div>
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={modeHistory}>
                  <defs>
                    <linearGradient id="vixG" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={accent} stopOpacity={.25} />
                      <stop offset="95%" stopColor={accent} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="run_date" tickFormatter={fmtDate}
                    tick={{ fill: '#5a6278', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    axisLine={false} tickLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#5a6278', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    axisLine={false} tickLine={false} width={30} />
                  <Tooltip content={<ChartTip />} />
                  <ReferenceLine y={18} stroke="#2dd4a040" strokeDasharray="3 3" label={{ value: 'VIX 18', fill: '#2dd4a040', fontSize: 9 }} />
                  <ReferenceLine y={22} stroke="#e0525240" strokeDasharray="3 3" label={{ value: 'VIX 22', fill: '#e0525240', fontSize: 9 }} />
                  <Area type="monotone" dataKey="vix" name="VIX"
                    stroke={accent} strokeWidth={1.5} fill="url(#vixG)" dot={false} />
                  <Line type="monotone" dataKey="ad_ratio" name="A/D"
                    stroke="#6eb3f7" strokeWidth={1} dot={false} strokeDasharray="3 3" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Movers */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
              <div className="card anim-2">
                <div className="label" style={{ marginBottom: 14 }}>
                  Top Score Movers
                </div>
                {(movers||[]).map(m => (
                  <div key={m.ticker} onClick={() => { setFocusTicker(m.ticker); setTab('signals') }}
                    style={{
                      display: 'flex', justifyContent: 'space-between',
                      padding: '8px 0', borderBottom: '1px solid var(--ink-2)', cursor: 'pointer',
                    }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <span style={{ fontSize: 13 }}>{m.ticker}</span>
                      <span className={`${scoreCls(m.omnivex_score)} mono`} style={{ fontSize: 11 }}>
                        {fmt(m.omnivex_score)}
                      </span>
                    </div>
                    <span className="mono" style={{
                      fontSize: 12,
                      color: (m.score_delta||0) >= 0 ? 'var(--alpha)' : 'var(--hedge)',
                    }}>
                      {(m.score_delta||0) >= 0 ? '+' : ''}{fmt(m.score_delta)}
                    </span>
                  </div>
                ))}
                {!movers?.length && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>
                    Requires 2+ daily runs
                  </div>
                )}
              </div>

              {/* Run history table */}
              <div className="card anim-2" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--ink-3)' }}>
                  <span className="label">Run History</span>
                </div>
                <div style={{ overflowY: 'auto', maxHeight: 360 }}>
                  <table className="pq-table">
                    <thead>
                      <tr>
                        <th>Date</th><th>Mode</th><th>VIX</th>
                        <th>SPY</th><th>Scored</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(runHistory||[]).map(r => (
                        <tr key={r.run_date}>
                          <td className="mono" style={{ color: 'var(--silver-2)' }}>
                            {fmtDate(r.run_date)}
                          </td>
                          <td><span className={`badge ${modeCls(r.mode)}`} style={{ fontSize: 8 }}>
                            {modeLabel(r.mode)}
                          </span></td>
                          <td className="mono">{fmt(r.vix)}</td>
                          <td className={`mono ${(r.spy_daily_pct||0)>=0?'c-pos':'c-neg'}`}>
                            {(r.spy_daily_pct||0)>=0?'+':''}{fmt(r.spy_daily_pct)}%
                          </td>
                          <td className="mono" style={{ color: 'var(--silver-2)' }}>
                            {r.tickers_scored}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* ══ TICKER DETAIL DRAWER ══ */}
      {focusTicker && (
        <div style={{
          position: 'fixed', right: 0, top: 58, bottom: 0,
          width: 320, background: 'var(--ink-1)',
          borderLeft: '1px solid var(--ink-4)',
          padding: 24, overflowY: 'auto', zIndex: 200,
          boxShadow: '-8px 0 32px rgba(0,0,0,.5)',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: 20,
          }}>
            <span style={{
              fontFamily: 'var(--font-serif)', fontSize: 24,
              color: 'var(--gold)', fontStyle: 'italic',
            }}>{focusTicker}</span>
            <button onClick={() => { setFocusTicker(null); setTickerHist(null) }}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--silver-2)', fontSize: 20, lineHeight: 1,
              }}>×</button>
          </div>

          {!tickerHist ? (
            <div className="label">Loading...</div>
          ) : (
            <>
              {/* Score chart */}
              {tickerHist.history?.length > 1 && (
                <div style={{ marginBottom: 20 }}>
                  <div className="label" style={{ marginBottom: 10 }}>Score History</div>
                  <ResponsiveContainer width="100%" height={110}>
                    <LineChart data={tickerHist.history}>
                      <XAxis dataKey="run_date" tickFormatter={fmtDate}
                        tick={{ fill: '#5a6278', fontSize: 9 }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0,100]} tick={{ fill: '#5a6278', fontSize: 9 }}
                        axisLine={false} tickLine={false} width={24} />
                      <Tooltip content={<ChartTip />} />
                      <Line type="monotone" dataKey="omnivex_score" name="Score"
                        stroke={accent} strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Current score breakdown */}
              {tickerHist.current && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  {[
                    ['Score', fmt(tickerHist.current.omnivex_score)],
                    ['Action', tickerHist.current.action || '—'],
                    ['QTech', fmt(tickerHist.current.qtech)],
                    ['PSOS', fmt(tickerHist.current.psos)],
                    ['Signal', fmt(tickerHist.current.signal_conf)],
                    ['Tier', tierLabel(tickerHist.current.tier)],
                  ].map(([k,v]) => (
                    <div key={k} style={{
                      background: 'var(--ink-2)', borderRadius: 6, padding: '10px 12px',
                    }}>
                      <div className="label" style={{ marginBottom: 4 }}>{k}</div>
                      <div style={{ fontSize: 14, fontWeight: 400 }}>{v}</div>
                    </div>
                  ))}
                </div>
              )}

              {tickerHist.history?.length === 0 && (
                <div style={{ color: 'var(--silver-2)', fontSize: 12 }}>
                  No history — first appearance today.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  )
}
