import { useState, useEffect, useMemo } from 'react'
import Head from 'next/head'
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, ReferenceLine
} from 'recharts'

// ─── Utilities ─────────────────────────────────────────────────────────────

const fmt     = (n, d = 1) => n == null || isNaN(n) ? '—' : Number(n).toFixed(d)
const fmtM    = (n) => n == null ? '—' : `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const fmtPct  = (n) => n == null ? '—' : `${n >= 0 ? '+' : ''}${fmt(n * 100, 2)}%`
const fmtDate = (d) => !d ? '—' : new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

function scoreCol(s) {
  if (s >= 80) return '#2de0aa'
  if (s >= 70) return '#60b8ff'
  if (s >= 60) return '#e0a832'
  if (s >= 50) return '#f07832'
  return '#f05555'
}
function scoreBg(s) {
  if (s >= 80) return '#2de0aa18'
  if (s >= 70) return '#60b8ff18'
  if (s >= 60) return '#e0a83218'
  if (s >= 50) return '#f0783218'
  return '#f0555518'
}
function scoreCls(s) {
  if (s >= 80) return 'c-breakout'
  if (s >= 70) return 'c-overweight'
  if (s >= 60) return 'c-maintain'
  if (s >= 50) return 'c-underweight'
  return 'c-exclude'
}
function scoreBand(s) {
  if (s >= 80) return 'Breakout'
  if (s >= 70) return 'Overweight'
  if (s >= 60) return 'Maintain'
  if (s >= 50) return 'Underweight'
  return 'Exclude'
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
function modeAccent(m) {
  if (m === 'ALPHA') return '#2de0aa'
  if (m === 'HEDGE') return '#f05555'
  return '#e0a832'
}
function tierLabel(t) {
  if (!t) return 'Monitor'
  return t.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())
}
function tierCol(t) {
  if (!t) return '#404868'
  if (t.includes('SMART')) return '#60b8ff'
  if (t.includes('TACTICAL')) return '#a090f0'
  if (t.includes('SPEC')) return '#e0a832'
  return '#404868'
}
function tierBg(t) {
  if (!t) return '#40486818'
  if (t.includes('SMART')) return '#60b8ff18'
  if (t.includes('TACTICAL')) return '#a090f018'
  if (t.includes('SPEC')) return '#e0a83218'
  return '#40486818'
}

// ─── Shared Components ─────────────────────────────────────────────────────

function ChartTip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0d0f18', border: '1px solid #232840',
      borderRadius: 8, padding: '10px 14px', fontSize: 12,
      fontFamily: 'var(--font-mono)',
    }}>
      <div style={{ color: '#6a7290', marginBottom: 6, fontSize: 11 }}>{fmtDate(label)}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, marginBottom: 2, fontWeight: 500 }}>
          {p.name}: {typeof p.value === 'number' ? fmt(p.value, 2) : p.value}
        </div>
      ))}
    </div>
  )
}

function StatCard({ label, value, sub, accent, className = 'anim-1' }) {
  return (
    <div className={`card card-sm ${className}`} style={{
      borderTop: `3px solid ${accent || '#232840'}`,
    }}>
      <div className="label" style={{ marginBottom: 12 }}>{label}</div>
      <div className="stat-value" style={{ color: accent || 'var(--text)' }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--silver-2)', marginTop: 6, fontWeight: 400 }}>{sub}</div>}
    </div>
  )
}

function ScorePill({ value }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: scoreBg(value),
      border: `1px solid ${scoreCol(value)}40`,
      borderRadius: 6, padding: '4px 10px',
      fontFamily: 'var(--font-mono)', fontSize: 15,
      fontWeight: 500, color: scoreCol(value),
      minWidth: 56, letterSpacing: '.02em',
    }}>
      {fmt(value)}
    </div>
  )
}

function MiniBar({ value, max = 100, color }) {
  return (
    <div style={{ width: 56, height: 4, background: '#232840', borderRadius: 2, marginTop: 4 }}>
      <div style={{
        height: '100%', borderRadius: 2,
        width: `${Math.min(100, (value / max) * 100)}%`,
        background: color || scoreCol(value),
      }} />
    </div>
  )
}

function TierPill({ tier }) {
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 500,
      letterSpacing: '.06em', textTransform: 'uppercase',
      padding: '3px 8px', borderRadius: 4,
      background: tierBg(tier), color: tierCol(tier),
      border: `1px solid ${tierCol(tier)}40`,
    }}>
      {tierLabel(tier)}
    </span>
  )
}

function SectionLabel({ children }) {
  return <div className="divider-label">{children}</div>
}

// ─── Main App ──────────────────────────────────────────────────────────────

export default function Omnivex() {
  const [mounted, setMounted] = useState(false)
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

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    Promise.all([
      fetch('/api/dashboard').then(r => r.json()),
      fetch('/api/portfolio').then(r => r.json()).catch(() => null),
    ]).then(([d, p]) => { setDashData(d); setPortData(p); setLoading(false) })
  }, [])

  useEffect(() => {
    if (!focusTicker) return
    setTickerHist(null)
    fetch(`/api/ticker?ticker=${focusTicker}`).then(r => r.json()).then(setTickerHist)
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
      .sort((a, b) => ((b[sortCol] ?? 0) - (a[sortCol] ?? 0)))
  }, [dashData, search, tierF, actionF, sortCol])

  const perfChart = useMemo(() => {
    const data = portData?.perfVsSpy
    if (!data?.length) return []
    let cumPort = 0, cumSpy = 0
    return data.map(d => {
      cumPort += (d.total_pnl_pct || 0) * 100
      cumSpy += (d.spy_daily_pct || 0) * 100
      return { date: d.snapshot_date, portfolio: +cumPort.toFixed(2), spy: +cumSpy.toFixed(2) }
    })
  }, [portData])

  // ── Loading ──
  if (loading) return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 24 }}>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 48, color: 'var(--gold)', fontStyle: 'italic', fontWeight: 500 }}>Omnivex</div>
      <div style={{ width: 56, height: 2, background: 'var(--gold)', opacity: .5 }} />
      <div className="label" style={{ letterSpacing: '.25em' }}>Paquette Capital</div>
    </div>
  )

  if (!dashData?.run) return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <div style={{ fontFamily: 'var(--font-serif)', fontSize: 32, color: 'var(--gold)', fontWeight: 500 }}>Awaiting First Run</div>
      <div style={{ color: 'var(--silver-2)', fontSize: 14 }}>Run the scorer to populate.</div>
      <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, background: 'var(--ink-2)', padding: '8px 16px', borderRadius: 6, color: 'var(--silver)' }}>python run_daily.py</code>
    </div>
  )

  const { run, modeHistory, movers, distribution, runHistory } = dashData
  const mode = run?.mode || 'CORE'
  const accent = modeAccent(mode)

  const holdings = portData?.holdings || []
  const trades = portData?.trades || []
  const allocation = portData?.allocation || []
  const snap = portData?.snapshot

  const totalValue = holdings.reduce((s, h) => s + (h.market_value || 0), 0)
  const totalPnl = holdings.reduce((s, h) => s + (h.unrealized_pnl || 0), 0)
  const totalCost = totalValue - totalPnl
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0

  const targetAlloc = {
    ALPHA: { SMART_CORE: 35, TACTICAL: 45, SPECULATIVE: 15, CASH: 5 },
    HEDGE: { SMART_CORE: 15, TACTICAL: 5,  SPECULATIVE: 0,  CASH: 80 },
    CORE:  { SMART_CORE: 52, TACTICAL: 25, SPECULATIVE: 7,  CASH: 16 },
  }[mode] || {}

  const actualAlloc = {}
  allocation.forEach(a => { actualAlloc[a.tier] = totalValue > 0 ? +((a.total_value / totalValue) * 100).toFixed(1) : 0 })

  return (
    <>
      <Head>
        <title>Omnivex — Paquette Capital</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      {/* ══ HEADER ══ */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(7,8,12,.95)', backdropFilter: 'blur(20px)',
        borderBottom: '1px solid var(--ink-4)', padding: '0 40px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 64,
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 20 }}>
          <span style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--gold)', fontStyle: 'italic', fontWeight: 500 }}>Omnivex</span>
          <span className="label" style={{ letterSpacing: '.22em', fontSize: 9 }}>Paquette Capital</span>
        </div>
        <nav style={{ display: 'flex' }}>
          {[['signals','Signals'],['portfolio','Portfolio'],['history','History']].map(([id,lbl]) => (
            <button key={id} className={`nav-tab ${tab===id?'active':''}`} onClick={() => setTab(id)}>{lbl}</button>
          ))}
        </nav>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span className={`badge ${modeCls(mode)}`}>{modeLabel(mode)}</span>
          {run?.chop_guard && <span className="badge badge-gold">Chop Guard</span>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="live-pip" />
            <span className="label" style={{ fontSize: 11 }}>{fmtDate(run?.run_date)}</span>
          </div>
        </div>
      </header>

      <main style={{ padding: '32px 40px', maxWidth: 1500, margin: '0 auto', position: 'relative', zIndex: 1 }}>

        {/* ══ SIGNALS TAB ══ */}
        {tab === 'signals' && (
          <div>
            {/* Stat cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: 12, marginBottom: 28 }}>
              {[
                ['Mode', modeLabel(mode), null, accent],
                ['VIX', fmt(run?.vix), null, run?.vix < 18 ? '#2de0aa' : run?.vix > 22 ? '#f05555' : '#e0a832'],
                ['SPY', `${(run?.spy_daily_pct||0)>=0?'+':''}${fmt(run?.spy_daily_pct)}%`, null, (run?.spy_daily_pct||0)>=0?'#2de0aa':'#f05555'],
                ['A/D Ratio', fmt(run?.ad_ratio,2), null, null],
                ['Yield Curve', run?.yield_curve_state||'—', null, run?.yield_curve_state==='INVERTED'?'#f05555':'#2de0aa'],
                ['Scored', run?.tickers_scored, `${run?.tickers_buy||0} buy · ${run?.tickers_reduce||0} reduce`, null],
                ['Alpha', `${run?.alpha_trigger_count||0}/6`, null, run?.alpha_trigger_count>=4?'#2de0aa':'#404868'],
                ['Hedge', `${run?.hedge_trigger_count||0}/5`, null, run?.hedge_trigger_count>=3?'#f05555':'#404868'],
              ].map(([label, value, sub, ac], i) => (
                <StatCard key={label} label={label} value={value} sub={sub} accent={ac}
                  className={`anim-${Math.min(4, Math.floor(i/2)+1)}`} />
              ))}
            </div>

            {/* Top picks row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16, marginBottom: 28 }}>

              {/* Buys */}
              <div className="card anim-2" style={{ borderTop: '3px solid var(--alpha)' }}>
                <div className="label" style={{ color: 'var(--alpha)', marginBottom: 18, fontSize: 11 }}>
                  ▲ Top Buy Candidates
                </div>
                {scores.filter(s => ['BUY','ADD'].includes(s.action)).slice(0,6).map(s => (
                  <div key={s.ticker} onClick={() => setFocusTicker(s.ticker)}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--ink-3)', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: '.02em' }}>{s.ticker}</span>
                      <TierPill tier={s.tier} />
                    </div>
                    <ScorePill value={s.omnivex_score} />
                  </div>
                ))}
                {scores.filter(s=>['BUY','ADD'].includes(s.action)).length===0 && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>None at current thresholds</div>
                )}
              </div>

              {/* Reduces */}
              <div className="card anim-2" style={{ borderTop: '3px solid var(--hedge)' }}>
                <div className="label" style={{ color: 'var(--hedge)', marginBottom: 18, fontSize: 11 }}>
                  ▼ Reduce / Rotate
                </div>
                {scores.filter(s=>['REDUCE','REMOVE','ROTATE'].includes(s.action)).slice(0,6).map(s => (
                  <div key={s.ticker} onClick={() => setFocusTicker(s.ticker)}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--ink-3)', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{s.ticker}</span>
                      <span className={`c-${(s.action||'').toLowerCase()}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500 }}>{s.action}</span>
                    </div>
                    <ScorePill value={s.omnivex_score} />
                  </div>
                ))}
                {scores.filter(s=>['REDUCE','REMOVE','ROTATE'].includes(s.action)).length===0 && (
                  <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>None flagged</div>
                )}
              </div>

              {/* System Alerts */}
              <div className="card anim-2" style={{ borderTop: '3px solid var(--gold)' }}>
                <div className="label" style={{ color: 'var(--gold)', marginBottom: 18, fontSize: 11 }}>System Alerts</div>

                {/* Mode proximity bars */}
                <div style={{ background: 'var(--ink-2)', borderRadius: 8, padding: '14px 16px', marginBottom: 14 }}>
                  <div className="label" style={{ marginBottom: 12 }}>Mode Proximity</div>
                  {[['Omnivex Alpha', run?.alpha_trigger_count||0, 6, 'var(--alpha)'],
                    ['Omnivex Hedge', run?.hedge_trigger_count||0, 5, 'var(--hedge)']].map(([name, count, total, color]) => (
                    <div key={name} style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                        <span style={{ fontSize: 12, color, fontWeight: 500 }}>{name}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--silver)' }}>{count}/{total}</span>
                      </div>
                      <div style={{ height: 5, background: 'var(--ink-4)', borderRadius: 3 }}>
                        <div style={{ height: '100%', borderRadius: 3, background: color, width: `${(count/total)*100}%`, transition: 'width .5s' }} />
                      </div>
                    </div>
                  ))}
                </div>

                {/* Forensic flags */}
                {scores.filter(s=>s.forensic_flag).length > 0 ? (
                  <>
                    <div className="label" style={{ color: 'var(--hedge)', marginBottom: 10, fontSize: 11 }}>⚠ Forensic Flags</div>
                    {scores.filter(s=>s.forensic_flag).slice(0,4).map(s => (
                      <div key={s.ticker} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--ink-3)' }}>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>{s.ticker}</span>
                        <span style={{ fontSize: 11, color: 'var(--silver-2)', maxWidth: 140, textAlign: 'right' }}>
                          {(s.forensic_detail||'').split('|')[0]}
                        </span>
                      </div>
                    ))}
                  </>
                ) : (
                  <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>No forensic flags today</div>
                )}
              </div>
            </div>

            {/* Score distribution */}
            {mounted && distribution?.length > 0 && (
              <div className="card anim-3" style={{ marginBottom: 28 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
                  <div className="label" style={{ fontSize: 11 }}>Score Distribution</div>
                  <div style={{ display: 'flex', gap: 16 }}>
                    {distribution.map(d => (
                      <div key={d.band} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                        <div style={{ width: 8, height: 8, borderRadius: 2, background: scoreCol(d.band==='Breakout'?85:d.band==='Overweight'?75:d.band==='Maintain'?65:d.band==='Underweight'?55:40) }} />
                        <span style={{ color: 'var(--silver-2)' }}>{d.band}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{d.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <ResponsiveContainer width="100%" height={80}>
                  <BarChart data={distribution} barSize={48} barGap={4}>
                    <XAxis dataKey="band" tick={{ fill: '#6a7290', fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 500 }} axisLine={false} tickLine={false} />
                    <YAxis hide />
                    <Tooltip contentStyle={{ background: '#0d0f18', border: '1px solid #232840', borderRadius: 8, fontSize: 12, fontFamily: 'var(--font-mono)' }} />
                    <Bar dataKey="count" radius={[4,4,0,0]}>
                      {distribution.map((d,i) => (
                        <Cell key={i} fill={scoreCol(d.band==='Breakout'?85:d.band==='Overweight'?75:d.band==='Maintain'?65:d.band==='Underweight'?55:40)} fillOpacity={.85} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Full table */}
            <div className="card anim-4" style={{ padding: 0, overflow: 'hidden' }}>
              {/* Controls */}
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--ink-3)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', background: 'var(--ink-2)' }}>
                <input className="pq-input" value={search} onChange={e => setSearch(e.target.value)}
                  placeholder="Search ticker or sector..." style={{ width: 220 }} />
                <div style={{ display: 'flex', gap: 8 }}>
                  {['ALL','SMART_CORE','TACTICAL','SPECULATIVE','MONITOR'].map(t => (
                    <button key={t} className={`filter-pill ${tierF===t?'active':''}`} onClick={() => setTierF(t)}>
                      {t.replace('_',' ')}
                    </button>
                  ))}
                </div>
                <select className="pq-input" value={actionF} onChange={e => setActionF(e.target.value)} style={{ width: 120 }}>
                  {['ALL','BUY','ADD','HOLD','REDUCE','REMOVE','ROTATE','MONITOR'].map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <span className="label" style={{ marginLeft: 'auto', fontSize: 11 }}>{scores.length} tickers</span>
              </div>

              {/* Table */}
              <div style={{ overflowX: 'auto' }}>
                <table className="pq-table">
                  <thead>
                    <tr>
                      {[
                        ['ticker','Ticker'], ['sector','Sector'], ['tier','Tier'],
                        ['omnivex_score','Score'], ['qtech','QTech'],
                        ['psos','PSOS'], ['signal_conf','Signal'],
                        ['action','Action'], ['suggested_weight_pct','Weight'],
                      ].map(([key, lbl]) => (
                        <th key={key} onClick={() => setSortCol(key)} style={{ cursor: 'pointer', userSelect: 'none' }}>
                          {lbl}{sortCol===key?' ↓':''}
                        </th>
                      ))}
                      <th>Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map(s => (
                      <tr key={s.ticker} onClick={() => setFocusTicker(s.ticker)}>
                        <td>
                          <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: '.02em' }}>{s.ticker}</span>
                        </td>
                        <td style={{ color: 'var(--silver)', fontSize: 12 }}>{s.sector||'—'}</td>
                        <td><TierPill tier={s.tier} /></td>
                        <td>
                          <ScorePill value={s.omnivex_score} />
                          <MiniBar value={s.omnivex_score} />
                        </td>
                        <td>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: scoreCol(s.qtech) }}>{fmt(s.qtech)}</span>
                          <MiniBar value={s.qtech} color={scoreCol(s.qtech)} />
                        </td>
                        <td>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: scoreCol(s.psos) }}>{fmt(s.psos)}</span>
                          <MiniBar value={s.psos} color={scoreCol(s.psos)} />
                        </td>
                        <td>
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 500, color: scoreCol(s.signal_conf) }}>{fmt(s.signal_conf)}</span>
                          <MiniBar value={s.signal_conf} color={scoreCol(s.signal_conf)} />
                        </td>
                        <td>
                          <span className={`c-${(s.action||'monitor').toLowerCase()}`}
                            style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, letterSpacing: '.04em' }}>
                            {s.action||'—'}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--silver)' }}>
                          {s.suggested_weight_pct ? `${fmt(s.suggested_weight_pct)}%` : '—'}
                        </td>
                        <td>
                          {s.forensic_flag && (
                            <span className="badge badge-hedge" style={{ fontSize: 9, marginRight: 4 }}>Forensic</span>
                          )}
                          {(s.flags||'').includes('EARNINGS_IMMINENT') && (
                            <span className="badge badge-gold" style={{ fontSize: 9 }}>Earnings</span>
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
              <div className="card" style={{ textAlign: 'center', padding: 80 }}>
                <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--gold)', marginBottom: 16, fontWeight: 500 }}>No Holdings</div>
                <div style={{ color: 'var(--silver-2)', fontSize: 14 }}>Connect Schwab or add holdings directly in Neon.</div>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 12, marginBottom: 28 }}>
                  <StatCard label="Total Value" value={fmtM(totalValue)} accent="var(--gold)" />
                  <StatCard label="Unrealized P&L" value={fmtM(totalPnl)}
                    sub={`${totalPnlPct>=0?'+':''}${fmt(totalPnlPct)}%`}
                    accent={totalPnl>=0?'var(--alpha)':'var(--hedge)'} />
                  <StatCard label="Positions" value={holdings.length} />
                  <StatCard label="Cash" value={fmtM(snap?.cash)} />
                  <StatCard label="Mode" value={modeLabel(mode)} accent={accent} />
                </div>

                {mounted && perfChart.length > 0 && (
                  <div className="card" style={{ marginBottom: 20 }}>
                    <div className="label" style={{ marginBottom: 18, fontSize: 11 }}>Performance vs SPY — Cumulative %</div>
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={perfChart}>
                        <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fill: '#6a7290', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                        <YAxis tick={{ fill: '#6a7290', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={42} tickFormatter={v => `${v>0?'+':''}${v.toFixed(1)}%`} />
                        <Tooltip content={<ChartTip />} />
                        <ReferenceLine y={0} stroke="#232840" strokeDasharray="4 4" />
                        <Line type="monotone" dataKey="portfolio" name="Omnivex" stroke={accent} strokeWidth={2.5} dot={false} />
                        <Line type="monotone" dataKey="spy" name="SPY" stroke="#404868" strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                  <div className="card">
                    <div className="label" style={{ marginBottom: 18, fontSize: 11 }}>Allocation — Target vs Actual</div>
                    {['SMART_CORE','TACTICAL','SPECULATIVE','CASH'].map(tier => {
                      const target = targetAlloc[tier] || 0
                      const actual = actualAlloc[tier] || 0
                      const col = tierCol(tier)
                      return (
                        <div key={tier} style={{ marginBottom: 18 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 500, color: col }}>{tierLabel(tier)}</span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                              <span style={{ color: 'var(--text)', fontWeight: 600 }}>{fmt(actual)}%</span>
                              <span style={{ color: 'var(--silver-2)' }}> / {fmt(target)}% target</span>
                            </span>
                          </div>
                          <div style={{ height: 4, background: 'var(--ink-3)', borderRadius: 2, marginBottom: 3 }}>
                            <div style={{ height: '100%', width: `${target}%`, background: col, opacity: .3, borderRadius: 2 }} />
                          </div>
                          <div style={{ height: 4, background: 'var(--ink-3)', borderRadius: 2 }}>
                            <div style={{ height: '100%', width: `${Math.min(100,actual)}%`, borderRadius: 2,
                              background: actual>target+5?'var(--hedge)':actual<target-5?'var(--core)':col }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="card">
                    <div className="label" style={{ marginBottom: 18, fontSize: 11 }}>Tier Performance</div>
                    <table className="pq-table">
                      <thead><tr><th>Tier</th><th>Pos</th><th>Value</th><th>P&L</th><th>Score</th></tr></thead>
                      <tbody>
                        {allocation.map(a => (
                          <tr key={a.tier}>
                            <td><TierPill tier={a.tier} /></td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{a.positions}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmtM(a.total_value)}</td>
                            <td className={`${a.total_pnl>=0?'c-pos':'c-neg'}`} style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{fmtM(a.total_pnl)}</td>
                            <td><ScorePill value={a.avg_score} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <SectionLabel>Current Holdings</SectionLabel>
                <div className="card" style={{ padding: 0, overflow: 'hidden', marginBottom: 24 }}>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="pq-table">
                      <thead><tr><th>Ticker</th><th>Tier</th><th>Shares</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>P&L</th><th>P&L %</th><th>Score</th><th>Action</th></tr></thead>
                      <tbody>
                        {holdings.map(h => (
                          <tr key={h.ticker} onClick={() => setFocusTicker(h.ticker)}>
                            <td><span style={{ fontWeight: 600, fontSize: 14 }}>{h.ticker}</span></td>
                            <td><TierPill tier={h.tier} /></td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmt(h.shares,2)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>${fmt(h.avg_cost,2)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>${fmt(h.current_price,2)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmtM(h.market_value)}</td>
                            <td className={(h.unrealized_pnl||0)>=0?'c-pos':'c-neg'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{fmtM(h.unrealized_pnl)}</td>
                            <td className={(h.unrealized_pnl_pct||0)>=0?'c-pos':'c-neg'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{fmtPct(h.unrealized_pnl_pct)}</td>
                            <td><ScorePill value={h.omnivex_score} /></td>
                            <td className={`c-${(h.action||'monitor').toLowerCase()}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>{h.action||'—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <SectionLabel>Trade Blotter</SectionLabel>
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="pq-table">
                      <thead><tr><th>Date</th><th>Ticker</th><th>Action</th><th>Shares</th><th>Price</th><th>Total</th><th>Score</th><th>Tier</th><th>Mode</th><th>Notes</th></tr></thead>
                      <tbody>
                        {trades.map(t => (
                          <tr key={t.id}>
                            <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--silver)' }}>{fmtDate(t.trade_date)}</td>
                            <td><span style={{ fontWeight: 600 }}>{t.ticker}</span></td>
                            <td className={`c-${(t.action||'').toLowerCase()}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600 }}>{t.action}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{fmt(t.shares,4)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>${fmt(t.price,2)}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmtM(t.total_value)}</td>
                            <td><ScorePill value={t.omnivex_score} /></td>
                            <td><TierPill tier={t.tier} /></td>
                            <td><span className={`badge ${modeCls(t.mode)}`} style={{ fontSize: 9 }}>{modeLabel(t.mode)}</span></td>
                            <td style={{ color: 'var(--silver-2)', fontSize: 12 }}>{t.notes||'—'}</td>
                          </tr>
                        ))}
                        {trades.length===0 && (
                          <tr><td colSpan={10} style={{ color: 'var(--silver-2)', textAlign: 'center', padding: 40, fontSize: 14 }}>No trades logged yet</td></tr>
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
            <div className="card anim-1" style={{ marginBottom: 20 }}>
              <div className="label" style={{ marginBottom: 18, fontSize: 11 }}>Market Context — 90 Days</div>
              {mounted && (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={modeHistory || []}>
                    <defs>
                      <linearGradient id="vixG" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={accent} stopOpacity={.3} />
                        <stop offset="95%" stopColor={accent} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="run_date" tickFormatter={fmtDate} tick={{ fill: '#6a7290', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                    <YAxis tick={{ fill: '#6a7290', fontSize: 11, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={32} />
                    <Tooltip content={<ChartTip />} />
                    <ReferenceLine y={18} stroke="#2de0aa30" strokeDasharray="3 3" />
                    <ReferenceLine y={22} stroke="#f0555530" strokeDasharray="3 3" />
                    <Area type="monotone" dataKey="vix" name="VIX" stroke={accent} strokeWidth={2} fill="url(#vixG)" dot={false} />
                    <Line type="monotone" dataKey="ad_ratio" name="A/D" stroke="#60b8ff" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="card anim-2">
                <div className="label" style={{ marginBottom: 18, fontSize: 11 }}>Top Score Movers</div>
                {(movers||[]).map(m => (
                  <div key={m.ticker} onClick={() => { setFocusTicker(m.ticker); setTab('signals') }}
                    style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid var(--ink-3)', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{m.ticker}</span>
                      <ScorePill value={m.omnivex_score} />
                    </div>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600,
                      color: (m.score_delta||0)>=0?'var(--alpha)':'var(--hedge)' }}>
                      {(m.score_delta||0)>=0?'+':''}{fmt(m.score_delta)}
                    </span>
                  </div>
                ))}
                {!movers?.length && <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>Requires 2+ daily runs</div>}
              </div>

              <div className="card anim-2" style={{ padding: 0, overflow: 'hidden' }}>
                <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--ink-3)', background: 'var(--ink-2)' }}>
                  <span className="label" style={{ fontSize: 11 }}>Run History</span>
                </div>
                <div style={{ overflowY: 'auto', maxHeight: 400 }}>
                  <table className="pq-table">
                    <thead><tr><th>Date</th><th>Mode</th><th>VIX</th><th>SPY</th><th>Tickers</th></tr></thead>
                    <tbody>
                      {(runHistory||[]).map(r => (
                        <tr key={r.run_date}>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmtDate(r.run_date)}</td>
                          <td><span className={`badge ${modeCls(r.mode)}`} style={{ fontSize: 9 }}>{modeLabel(r.mode)}</span></td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 500 }}>{fmt(r.vix)}</td>
                          <td className={(r.spy_daily_pct||0)>=0?'c-pos':'c-neg'} style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                            {(r.spy_daily_pct||0)>=0?'+':''}{fmt(r.spy_daily_pct)}%
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--silver)' }}>{r.tickers_scored}</td>
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

      {/* ══ TICKER DRAWER ══ */}
      {focusTicker && (
        <div style={{
          position: 'fixed', right: 0, top: 64, bottom: 0, width: 340,
          background: 'var(--ink-1)', borderLeft: '1px solid var(--ink-4)',
          padding: 28, overflowY: 'auto', zIndex: 200,
          boxShadow: '-12px 0 40px rgba(0,0,0,.6)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <span style={{ fontFamily: 'var(--font-serif)', fontSize: 28, color: 'var(--gold)', fontStyle: 'italic', fontWeight: 500 }}>{focusTicker}</span>
            <button onClick={() => { setFocusTicker(null); setTickerHist(null) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--silver-2)', fontSize: 24, lineHeight: 1 }}>×</button>
          </div>

          {!tickerHist ? (
            <div className="label">Loading...</div>
          ) : (
            <>
              {mounted && tickerHist.history?.length > 1 && (
                <div style={{ marginBottom: 24 }}>
                  <div className="label" style={{ marginBottom: 12, fontSize: 11 }}>Score History</div>
                  <ResponsiveContainer width="100%" height={120}>
                    <LineChart data={tickerHist.history}>
                      <XAxis dataKey="run_date" tickFormatter={fmtDate} tick={{ fill: '#6a7290', fontSize: 10 }} axisLine={false} tickLine={false} />
                      <YAxis domain={[0,100]} tick={{ fill: '#6a7290', fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
                      <Tooltip content={<ChartTip />} />
                      <Line type="monotone" dataKey="omnivex_score" name="Score" stroke={accent} strokeWidth={2.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
              {tickerHist.current && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  {[
                    ['Score', <ScorePill value={tickerHist.current.omnivex_score} />],
                    ['Action', <span className={`c-${(tickerHist.current.action||'monitor').toLowerCase()}`} style={{ fontFamily: 'var(--font-mono)', fontSize: 14, fontWeight: 600 }}>{tickerHist.current.action||'—'}</span>],
                    ['QTech', <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: scoreCol(tickerHist.current.qtech) }}>{fmt(tickerHist.current.qtech)}</span>],
                    ['PSOS', <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: scoreCol(tickerHist.current.psos) }}>{fmt(tickerHist.current.psos)}</span>],
                    ['Signal', <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 600, color: scoreCol(tickerHist.current.signal_conf) }}>{fmt(tickerHist.current.signal_conf)}</span>],
                    ['Tier', <TierPill tier={tickerHist.current.tier} />],
                  ].map(([k,v]) => (
                    <div key={k} style={{ background: 'var(--ink-2)', borderRadius: 8, padding: '12px 14px' }}>
                      <div className="label" style={{ marginBottom: 8, fontSize: 10 }}>{k}</div>
                      <div>{v}</div>
                    </div>
                  ))}
                </div>
              )}
              {tickerHist.history?.length === 0 && (
                <div style={{ color: 'var(--silver-2)', fontSize: 13 }}>No history — first appearance today.</div>
              )}
            </>
          )}
        </div>
      )}
    </>
  )
}