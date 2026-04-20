"""
OMNIVEX — Output Engine
Layer 1: Terminal (CLI)
Layer 2: CSV Audit Log
Layer 3: HTML Dashboard Report
"""

import csv
import os
from datetime import datetime
from core.config import (
    TODAY, CSV_PATH, HTML_PATH, LOG_DIR, REPORT_DIR,
    STAGE2_ACTIONS, STAGE3_AUTO_ACTIONS, EXECUTION_STAGE,
    interpret_score, recommend_action,
)


# ─────────────────────────────────────────────
# ENSURE DIRS EXIST
# ─────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# LAYER 1 — TERMINAL OUTPUT
# ─────────────────────────────────────────────

def print_terminal_report(mode_result: dict, scored: list,
                           portfolio: dict = None):
    """Print formatted terminal report."""
    from colorama import Fore, Style, init
    init(autoreset=True)

    mode = mode_result["mode"]
    mode_colors = {
        "ALPHA": Fore.GREEN,
        "HEDGE": Fore.RED,
        "CORE": Fore.YELLOW,
    }
    mc = mode_colors.get(mode, Fore.WHITE)

    chop = " + CHOP GUARD" if mode_result.get("chop_guard_active") else ""

    print(f"\n{Fore.CYAN}{'═'*55}")
    print(f"  OMNIVEX — PAQUETTE CAPITAL — {TODAY}")
    print(f"{'═'*55}{Style.RESET_ALL}")

    vix = mode_result.get("vix", "N/A")
    spy_pct = mode_result.get("spy_daily_pct", 0) or 0
    spy_str = f"+{spy_pct:.1f}%" if spy_pct >= 0 else f"{spy_pct:.1f}%"
    ad = mode_result.get("ad_ratio", "N/A")
    yc = mode_result.get("yield_curve_state", "UNKNOWN")

    print(f"  MODE: {mc}{mode}{chop}{Style.RESET_ALL}  |  "
          f"VIX: {vix}  |  SPY: {spy_str}")
    print(f"  A/D: {ad}  |  Yield Curve: {yc}")

    # Trigger counts
    t_count = mode_result['alpha_trigger_count']
    a_count = mode_result['hedge_trigger_count']
    print(f"  Omnivex Alpha: {t_count}/6 triggers  |  Omnivex Hedge: {a_count}/5 triggers")

    mode_watch = mode_result.get("mode_shift_watch", "")
    if mode_watch and "⚠" in mode_watch:
        print(f"  {Fore.YELLOW}{mode_watch}{Style.RESET_ALL}")

    print(f"{Fore.CYAN}{'─'*55}{Style.RESET_ALL}")

    # Top actions
    top_buys = [s for s in scored if s.get("action") in ("BUY", "ADD")][:5]
    top_reduces = [s for s in scored if s.get("action") in ("REDUCE", "REMOVE", "ROTATE")][:3]

    if top_buys:
        print(f"  {Fore.GREEN}TOP BUY CANDIDATES{Style.RESET_ALL}")
        for s in top_buys:
            _print_action_line(s)

    if top_reduces:
        print(f"  {Fore.RED}REDUCE / ROTATE{Style.RESET_ALL}")
        for s in top_reduces:
            _print_action_line(s)

    # Flags
    flagged = [s for s in scored if s.get("flags")]
    if flagged:
        print(f"{Fore.CYAN}{'─'*55}{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}FLAGS{Style.RESET_ALL}")
        for s in flagged:
            ticker = s["ticker"]
            for flag in s["flags"]:
                if flag == "FORENSIC":
                    ff = ", ".join(s.get("forensic_flags", []))
                    print(f"  {Fore.RED}⚠ {ticker} — Forensic: {ff}{Style.RESET_ALL}")
                elif flag == "EARNINGS_IMMINENT":
                    print(f"  {Fore.YELLOW}⚠ {ticker} — Earnings within 7 days{Style.RESET_ALL}")
                elif flag == "DATA_PARTIAL":
                    print(f"  {Fore.WHITE}⚠ {ticker} — Partial data{Style.RESET_ALL}")

    # Human review required
    needs_review = [s for s in scored if _needs_human_review(s)]
    if needs_review:
        print(f"  {Fore.YELLOW}Human review required: "
              f"{len(needs_review)} position(s){Style.RESET_ALL}")

    print(f"{Fore.CYAN}{'═'*55}{Style.RESET_ALL}\n")


def _print_action_line(s: dict):
    from colorama import Fore, Style
    action = s.get("action", "MONITOR")
    ticker = s["ticker"]
    score = s.get("omnivex_score", 0)
    tier = s.get("tier", "UNKNOWN")
    weight = s.get("suggested_weight_pct", 0)
    flags = " ".join(f"[{f}]" for f in s.get("flags", []))

    action_colors = {
        "BUY": Fore.GREEN, "ADD": Fore.GREEN,
        "HOLD": Fore.WHITE, "MONITOR": Fore.WHITE,
        "REDUCE": Fore.YELLOW, "ROTATE": Fore.YELLOW,
        "REMOVE": Fore.RED,
    }
    ac = action_colors.get(action, Fore.WHITE)

    print(f"  {ac}{action:<8}{Style.RESET_ALL} "
          f"{ticker:<6}  Score:{score:>5.1f}  "
          f"Tier:{tier:<12}  Wt:{weight:.1f}%  {flags}")


# ─────────────────────────────────────────────
# LAYER 2 — CSV AUDIT LOG
# ─────────────────────────────────────────────

CSV_COLUMNS = [
    "Date", "Mode", "ChopGuard", "Ticker", "Sector", "Industry",
    "Market_Cap", "Tier", "Omnivex", "QTech", "PSOS_raw", "PSOS",
    "Signal_Conf", "Action", "Suggested_Weight_Pct",
    "Override_Flag", "Override_Reason", "Forensic_Flag", "Forensic_Detail",
    "Earnings_Proximity_Days", "Data_Quality",
    "VIX", "AD_Ratio", "SPY_vs_50DMA", "SPY_vs_200DMA", "Yield_Curve_State",
    "RSI_Score", "Momentum_Score", "Volume_Score", "Insider_Score",
    "Analyst_Score", "Trend_Score",
    "ROIC_Score", "PEG_Score", "FCF_Score", "Margin_Score", "Debt_Score", "RevGrowth_Score",
    "Flags", "Timestamp",
]


def write_csv(mode_result: dict, scored: list, path: str = None):
    """Append all scored tickers to daily CSV audit log."""
    path = path or CSV_PATH
    write_header = not os.path.exists(path)

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        mode = mode_result["mode"]
        chop = mode_result.get("chop_guard_active", False)
        vix = mode_result.get("vix", "")
        ad = mode_result.get("ad_ratio", "")
        spy50 = mode_result.get("spy_above_50dma", "")
        spy200 = mode_result.get("spy_above_200dma", "")
        yc = mode_result.get("yield_curve_state", "")
        ts = datetime.now().isoformat()

        for s in scored:
            qd = s.get("qtech_detail", {}).get("components", {})
            scd = s.get("signal_confidence_detail", {}).get("components", {})

            row = {
                "Date": TODAY,
                "Mode": mode,
                "ChopGuard": chop,
                "Ticker": s["ticker"],
                "Sector": s.get("sector", ""),
                "Industry": s.get("industry", ""),
                "Market_Cap": s.get("market_cap", ""),
                "Tier": s.get("tier", ""),
                "Omnivex": s.get("omnivex_score", ""),
                "QTech": s.get("qtech", ""),
                "PSOS_raw": s.get("psos_raw", ""),
                "PSOS": s.get("psos", ""),
                "Signal_Conf": s.get("signal_confidence", ""),
                "Action": s.get("action", ""),
                "Suggested_Weight_Pct": s.get("suggested_weight_pct", ""),
                "Override_Flag": s.get("override_applied", False),
                "Override_Reason": s.get("override_reason", ""),
                "Forensic_Flag": bool(s.get("forensic_flags")),
                "Forensic_Detail": "|".join(s.get("forensic_flags", [])),
                "Earnings_Proximity_Days": s.get("psos_detail", {}).get("p_components", {}).get("earnings_proximity", ""),
                "Data_Quality": s.get("data_quality", ""),
                "VIX": vix,
                "AD_Ratio": ad,
                "SPY_vs_50DMA": spy50,
                "SPY_vs_200DMA": spy200,
                "Yield_Curve_State": yc,
                "RSI_Score": scd.get("rsi_strength", ""),
                "Momentum_Score": scd.get("momentum", ""),
                "Volume_Score": scd.get("volume_expansion", ""),
                "Insider_Score": scd.get("insider_activity", ""),
                "Analyst_Score": scd.get("analyst_direction", ""),
                "Trend_Score": scd.get("trend_alignment", ""),
                "ROIC_Score": qd.get("roic", ""),
                "PEG_Score": qd.get("peg", ""),
                "FCF_Score": qd.get("fcf_stability", ""),
                "Margin_Score": qd.get("gross_margin", ""),
                "Debt_Score": qd.get("debt_health", ""),
                "RevGrowth_Score": qd.get("revenue_growth", ""),
                "Flags": "|".join(s.get("flags", [])),
                "Timestamp": ts,
            }
            writer.writerow(row)

    return path


# ─────────────────────────────────────────────
# LAYER 3 — HTML DASHBOARD
# ─────────────────────────────────────────────

def write_html(mode_result: dict, scored: list, path: str = None):
    """Generate full HTML dashboard report."""
    path = path or HTML_PATH

    mode = mode_result["mode"]
    mode_colors = {"ALPHA": "#22c55e", "HEDGE": "#ef4444", "CORE": "#f59e0b"}
    mc = mode_colors.get(mode, "#94a3b8")

    rows_html = ""
    for s in scored:
        score = s.get("omnivex_score", 0)
        action = s.get("action", "MONITOR")
        flags = s.get("flags", [])

        score_color = (
            "#22c55e" if score >= 80 else
            "#3b82f6" if score >= 70 else
            "#f59e0b" if score >= 60 else
            "#f97316" if score >= 50 else
            "#ef4444"
        )
        action_color = (
            "#22c55e" if action in ("BUY", "ADD") else
            "#f97316" if action in ("REDUCE", "ROTATE") else
            "#ef4444" if action in ("REMOVE",) else
            "#94a3b8"
        )
        flag_html = " ".join(
            f'<span class="flag flag-{f.lower()}">{f}</span>'
            for f in flags
        )
        review_badge = (
            '<span class="flag flag-review">REVIEW</span>'
            if _needs_human_review(s) else ""
        )

        scenarios = s.get("psos_detail", {}).get("scenarios", {})
        bull_scenarios = scenarios.get("bull", [])
        bear_scenarios = scenarios.get("bear", [])
        scenario_html = ""
        if bull_scenarios or bear_scenarios:
            bulls_txt = " / ".join(bull_scenarios) if bull_scenarios else "—"
            bears_txt = " / ".join(bear_scenarios) if bear_scenarios else "—"
            scenario_html = (
                f'<div style="font-size:10px;color:#94a3b8;margin-top:4px">'
                f'<span style="color:#22c55e">▲</span> {bulls_txt}<br>'
                f'<span style="color:#ef4444">▼</span> {bears_txt}</div>'
            )

        rows_html += f"""
        <tr>
            <td><strong>{s['ticker']}</strong>{scenario_html}</td>
            <td>{s.get('sector','')}</td>
            <td><span class="tier-badge">{s.get('tier','')}</span></td>
            <td style="color:{score_color};font-weight:600">{score:.1f}</td>
            <td>{s.get('qtech',0):.1f}</td>
            <td>{s.get('psos',0):.1f}</td>
            <td>{s.get('signal_confidence',0):.1f}</td>
            <td style="color:{action_color};font-weight:600">{action}</td>
            <td>{s.get('suggested_weight_pct',0):.1f}%</td>
            <td>{flag_html}{review_badge}</td>
        </tr>"""

    top_buys = [s for s in scored if s.get("action") in ("BUY", "ADD")][:5]
    top_reduce = [s for s in scored if s.get("action") in ("REDUCE", "REMOVE", "ROTATE")][:3]
    flagged_count = len([s for s in scored if s.get("flags")])
    review_count = len([s for s in scored if _needs_human_review(s)])

    top_buys_html = "".join(
        f"<li><strong>{s['ticker']}</strong> — {s.get('omnivex_score',0):.1f} "
        f"({s.get('tier','')}) → {s.get('action','')}</li>"
        for s in top_buys
    )
    top_reduce_html = "".join(
        f"<li><strong>{s['ticker']}</strong> — {s.get('omnivex_score',0):.1f} "
        f"→ {s.get('action','')}</li>"
        for s in top_reduce
    )

    chop_badge = (
        '<span style="background:#f59e0b;color:#000;padding:2px 8px;'
        'border-radius:4px;font-size:11px;margin-left:8px">CHOP GUARD</span>'
        if mode_result.get("chop_guard_active") else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Omnivex Daily Report — {TODAY}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
  h1 {{ font-size:22px; font-weight:600; margin:0 0 4px; }}
  .subtitle {{ color:#94a3b8; font-size:13px; margin-bottom:24px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
           gap:12px; margin-bottom:24px; }}
  .card {{ background:#1e293b; border-radius:8px; padding:16px; }}
  .card-label {{ font-size:11px; color:#94a3b8; text-transform:uppercase;
                 letter-spacing:.05em; margin-bottom:6px; }}
  .card-value {{ font-size:22px; font-weight:600; }}
  .section {{ background:#1e293b; border-radius:8px; padding:20px;
              margin-bottom:20px; }}
  .section h2 {{ font-size:14px; font-weight:600; color:#94a3b8;
                 text-transform:uppercase; letter-spacing:.05em;
                 margin:0 0 16px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; padding:8px 12px; color:#94a3b8; font-weight:500;
        border-bottom:1px solid #334155; }}
  td {{ padding:8px 12px; border-bottom:1px solid #1e293b; }}
  tr:hover td {{ background:#0f172a; }}
  .flag {{ display:inline-block; font-size:10px; padding:2px 6px;
           border-radius:3px; margin-right:3px; font-weight:600; }}
  .flag-forensic {{ background:#fee2e2; color:#991b1b; }}
  .flag-earnings_imminent {{ background:#fef3c7; color:#92400e; }}
  .flag-earnings_near {{ background:#fef9c3; color:#a16207; }}
  .flag-override {{ background:#e0e7ff; color:#3730a3; }}
  .flag-data_partial {{ background:#f3f4f6; color:#374151; }}
  .flag-review {{ background:#fde68a; color:#92400e; }}
  .flag-crowd_overload {{ background:#fce7f3; color:#9d174d; }}
  .tier-badge {{ font-size:10px; padding:2px 6px; border-radius:3px;
                 background:#334155; color:#cbd5e1; }}
  ul {{ margin:0; padding-left:18px; }}
  li {{ margin-bottom:6px; font-size:13px; }}
  .trigger-row {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }}
  .trigger {{ font-size:11px; padding:3px 8px; border-radius:4px; }}
  .trigger-on {{ background:#22c55e22; color:#22c55e; border:1px solid #22c55e44; }}
  .trigger-off {{ background:#ef444422; color:#ef4444; border:1px solid #ef444444; }}
</style>
</head>
<body>
<h1>Omnivex Daily</h1>
<p class="subtitle">{TODAY} &nbsp;|&nbsp;
  <span style="color:{mc};font-weight:600">{mode} MODE</span>{chop_badge}
  &nbsp;|&nbsp; Generated {datetime.now().strftime('%H:%M')}
</p>

<!-- SUMMARY CARDS -->
<div class="grid">
  <div class="card">
    <div class="card-label">Mode</div>
    <div class="card-value" style="color:{mc}">{mode}</div>
  </div>
  <div class="card">
    <div class="card-label">VIX</div>
    <div class="card-value">{mode_result.get('vix','N/A')}</div>
  </div>
  <div class="card">
    <div class="card-label">SPY</div>
    <div class="card-value">{('+' if (mode_result.get('spy_daily_pct') or 0) >= 0 else '')}{mode_result.get('spy_daily_pct','N/A'):.1f}%</div>
  </div>
  <div class="card">
    <div class="card-label">A/D Ratio</div>
    <div class="card-value">{mode_result.get('ad_ratio','N/A')}</div>
  </div>
  <div class="card">
    <div class="card-label">Yield Curve</div>
    <div class="card-value" style="font-size:14px">{mode_result.get('yield_curve_state','N/A')}</div>
  </div>
  <div class="card">
    <div class="card-label">Tickers Scored</div>
    <div class="card-value">{len(scored)}</div>
  </div>
  <div class="card">
    <div class="card-label">Flags</div>
    <div class="card-value" style="color:#f59e0b">{flagged_count}</div>
  </div>
  <div class="card">
    <div class="card-label">Needs Review</div>
    <div class="card-value" style="color:#ef4444">{review_count}</div>
  </div>
</div>

<!-- TOP ACTIONS -->
<div class="section">
  <h2>Executive Summary</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
    <div>
      <p style="color:#22c55e;font-size:12px;font-weight:600;margin:0 0 8px">
        TOP BUY CANDIDATES
      </p>
      <ul>{top_buys_html or '<li style="color:#94a3b8">None at current thresholds</li>'}</ul>
    </div>
    <div>
      <p style="color:#ef4444;font-size:12px;font-weight:600;margin:0 0 8px">
        REDUCE / ROTATE
      </p>
      <ul>{top_reduce_html or '<li style="color:#94a3b8">None flagged</li>'}</ul>
    </div>
  </div>
  <div style="margin-top:16px;padding-top:16px;border-top:1px solid #334155">
    <p style="font-size:12px;color:#94a3b8;margin:0">
      Mode shift: {mode_result.get('mode_shift_watch','Stable')}
      &nbsp;|&nbsp; Omnivex Alpha: {mode_result['alpha_trigger_count']}/6
      &nbsp;|&nbsp; Omnivex Hedge: {mode_result['hedge_trigger_count']}/5
    </p>
  </div>
</div>

<!-- FULL RANKED TABLE -->
<div class="section">
  <h2>Full Ranked Universe ({len(scored)} tickers)</h2>
  <table>
    <thead>
      <tr>
        <th>Ticker</th><th>Sector</th><th>Tier</th>
        <th>Score</th><th>QTech</th><th>PSOS</th><th>Sig.Conf</th>
        <th>Action</th><th>Weight</th><th>Flags</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>

</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return path


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _needs_human_review(s: dict) -> bool:
    from core.config import HUMAN_REVIEW_TRIGGERS
    if s.get("signal_confidence", 100) < HUMAN_REVIEW_TRIGGERS["signal_confidence_min"]:
        return True
    if "FORENSIC" in s.get("flags", []):
        return True
    if s.get("tier") == "SPECULATIVE":
        return True
    if s.get("override_applied"):
        return True
    if "EARNINGS_IMMINENT" in s.get("flags", []):
        return True
    if s.get("action") == "ROTATE":
        return True
    return False


def assign_action(s: dict, portfolio: dict = None, mode: str = "CORE") -> str:
    """Assign action based on score and current portfolio state."""
    ticker = s["ticker"]
    score = s.get("omnivex_score", 0)
    has_position = portfolio.get(ticker, 0) > 0 if portfolio else False

    if "FORENSIC" in s.get("flags", []):
        return "REMOVE" if has_position else "EXCLUDE"

    if score >= 80:
        return "BUY" if not has_position else "ADD"
    elif score >= 70:
        return "ADD" if has_position else "BUY"
    elif score >= 60:
        return "HOLD" if has_position else "MONITOR"
    elif score >= 50:
        return "REDUCE" if has_position else "MONITOR"
    else:
        return "REMOVE" if has_position else "EXCLUDE"


def calc_suggested_weight(s: dict, mode: str = "CORE") -> float:
    """Suggest position weight % based on tier, score, and mode."""
    from core.config import POSITION_SIZING, CHOP_GUARD
    tier = s.get("tier", "MONITOR")
    score = s.get("omnivex_score", 0)

    sizing = POSITION_SIZING.get(tier.upper(), None)
    if not sizing:
        return 0.0

    base_low, base_high = sizing["base"]
    base = (base_low + base_high) / 2
    max_weight = sizing["max"]

    bonus = 0.0
    if score >= sizing["score_bonus_threshold"]:
        bonus += 0.01
    if "ceo_insider_buy" in s.get("adjustment_log", []):
        bonus += 0.01

    weight = min(base + bonus, max_weight) * 100  # as percentage
    return round(weight, 1)
