"""
OMNIVEX — Scoring Engine
QTech + PSOS + Signal Confidence → Omnivex Score
All formulas sourced directly from knowledge base v2.3
"""

import math
from core.config import (
    OMNIVEX_WEIGHTS, QTECH_WEIGHTS, SIGNAL_CONF_WEIGHTS,
    PSOS_PROBABILITY_WEIGHTS, PSOS_SEVERITY_WEIGHTS,
    PSOS_OPPORTUNITY_WEIGHTS, PSOS_CLARITY_WEIGHTS,
    ANALYST_EVENT_SCORES, ANALYST_SOURCE_WEIGHTS, ANALYST_RECENCY_WEIGHTS,
    INSIDER_SCORE_MAP, INSIDER_HEAVY_SELL_SCORE,
    SCORE_ADJUSTMENTS, SPECULATIVE_REQUIREMENTS,
    SMART_CORE_HARD_GATES, SECTOR_THRESHOLDS,
    interpret_score, score_rsi,
)


# ─────────────────────────────────────────────
# MASTER SCORER
# ─────────────────────────────────────────────

def score_ticker(data: dict, market_ctx: dict, spy_momentum: dict,
                 analyst_events: list = None, insider_events: list = None,
                 manual_override: float = None, manual_override_reason: str = None) -> dict:
    """
    Score a single ticker. Returns full score breakdown dict.
    
    data: output from fetcher.get_ticker_data()
    market_ctx: output from fetcher.get_market_context()
    spy_momentum: {spy_3m, spy_6m}
    analyst_events: list of dicts {event_type, source_tier, days_ago}
    insider_events: list of dicts {title, buy_value, is_open_market_buy}
    manual_override: float in [-10, +10] — logged with reason
    """
    result = {
        "ticker": data["ticker"],
        "sector": data.get("sector", "Unknown"),
        "industry": data.get("industry", "Unknown"),
        "market_cap": data.get("market_cap"),
        "data_quality": data.get("data_quality", "OK"),
        "flags": [],
        "forensic_flags": [],
        "override_applied": False,
        "override_reason": None,
    }

    # ── QTech ──
    qtech_detail = calc_qtech(data)
    result["qtech"] = qtech_detail["score"]
    result["qtech_detail"] = qtech_detail

    # ── PSOS ──
    psos_detail = calc_psos(data, market_ctx, analyst_events or [])
    result["psos_raw"] = psos_detail["psos_raw"]
    result["psos"] = psos_detail["psos_normalized"]
    result["psos_detail"] = psos_detail

    # ── Signal Confidence ──
    sc_detail = calc_signal_confidence(
        data, market_ctx, spy_momentum, analyst_events or [], insider_events or []
    )
    result["signal_confidence"] = sc_detail["score"]
    result["signal_confidence_detail"] = sc_detail

    # ── Raw Omnivex Score ──
    raw_score = (
        OMNIVEX_WEIGHTS["qtech"] * result["qtech"]
        + OMNIVEX_WEIGHTS["psos"] * result["psos"]
        + OMNIVEX_WEIGHTS["signal_confidence"] * result["signal_confidence"]
    )

    # ── Adjustments ──
    adjustments = 0
    adjustment_log = []

    analyst_cluster = _has_analyst_cluster(analyst_events or [])
    if analyst_cluster:
        adjustments += SCORE_ADJUSTMENTS["analyst_upgrade_cluster"]
        adjustment_log.append(f"analyst_cluster: +{SCORE_ADJUSTMENTS['analyst_upgrade_cluster']}")

    ceo_buy = _has_ceo_buy(insider_events or [])
    if ceo_buy:
        adjustments += SCORE_ADJUSTMENTS["ceo_insider_buy"]
        adjustment_log.append(f"ceo_insider_buy: +{SCORE_ADJUSTMENTS['ceo_insider_buy']}")

    forensic = _check_forensic_flags(data)
    if forensic:
        adjustments += SCORE_ADJUSTMENTS["forensic_red_flag"]
        result["forensic_flags"] = forensic
        result["flags"].append("FORENSIC")
        adjustment_log.append(f"forensic_flag: {SCORE_ADJUSTMENTS['forensic_red_flag']}")

    retail_crowded = _is_retail_crowded(data)
    if retail_crowded:
        adjustments += SCORE_ADJUSTMENTS["retail_crowding"]
        result["flags"].append("CROWD_OVERLOAD")
        adjustment_log.append(f"retail_crowding: {SCORE_ADJUSTMENTS['retail_crowding']}")

    result["adjustments"] = round(adjustments, 2)
    result["adjustment_log"] = adjustment_log

    adjusted_score = raw_score + adjustments

    # ── Manual Override (±10 pts max) ──
    if manual_override is not None:
        capped = max(-10.0, min(10.0, manual_override))
        adjusted_score += capped
        result["override_applied"] = True
        result["override_reason"] = manual_override_reason or "No reason provided"
        result["flags"].append("OVERRIDE")

    # ── Final Score ──
    final_score = round(max(0, min(100, adjusted_score)), 2)
    result["omnivex_score"] = final_score
    result["interpretation"] = interpret_score(final_score)

    # ── Tier Classification ──
    result["tier"] = classify_tier(result, data)

    # ── Smart Core Gate Check ──
    result["passes_smart_core_gates"] = check_smart_core_gates(data)

    # ── Additional Flags ──
    if data.get("signal_confidence") and result["signal_confidence"] < 40:
        result["flags"].append("LOW_CONFIDENCE")

    if data.get("earnings_proximity_days") is not None:
        days = data["earnings_proximity_days"]
        if 0 <= days <= 7:
            result["flags"].append("EARNINGS_IMMINENT")
        elif 0 <= days <= 14:
            result["flags"].append("EARNINGS_NEAR")

    if data.get("data_quality") == "PARTIAL":
        result["flags"].append("DATA_PARTIAL")
    elif data.get("data_quality") == "MISSING":
        result["flags"].append("DATA_MISSING")

    return result


# ─────────────────────────────────────────────
# QTECH SCORE
# ─────────────────────────────────────────────

def calc_qtech(data: dict) -> dict:
    """
    QTech = 0.25×ROIC + 0.20×PEG + 0.15×FCF + 0.15×GrossMargin + 0.10×Debt + 0.15×RevGrowth
    """
    components = {}

    # ROIC Score
    roic = data.get("roic")
    if roic is not None:
        roic_pct = roic * 100 if roic < 2 else roic  # normalize if decimal
        if roic_pct >= 20:
            components["roic"] = 100
        elif roic_pct >= 15:
            components["roic"] = 85
        elif roic_pct >= 10:
            components["roic"] = 70
        else:
            components["roic"] = 40
    else:
        components["roic"] = 50  # neutral on missing

    # PEG Score
    peg = data.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg < 1.0:
            components["peg"] = 100
        elif peg < 1.5:
            components["peg"] = 80
        elif peg < 2.0:
            components["peg"] = 60
        else:
            components["peg"] = 40
    else:
        components["peg"] = 50

    # FCF Stability
    fcf = data.get("fcf")
    fcf_yield = data.get("fcf_yield")
    if fcf is not None:
        if fcf > 0 and fcf_yield and fcf_yield > 0.03:
            components["fcf_stability"] = 90
        elif fcf > 0:
            components["fcf_stability"] = 70
        elif fcf < 0:
            components["fcf_stability"] = 30
        else:
            components["fcf_stability"] = 50
    else:
        components["fcf_stability"] = 50

    # Gross Margin Strength (normalized vs sector)
    gm = data.get("gross_margin")
    sector = data.get("sector", "default")
    thresholds = SECTOR_THRESHOLDS.get(sector, SECTOR_THRESHOLDS["default"])
    gm_min = thresholds.get("gross_margin_min", 0.40)
    if gm is not None and gm_min is not None:
        if gm >= gm_min * 1.5:
            components["gross_margin"] = 100
        elif gm >= gm_min * 1.2:
            components["gross_margin"] = 85
        elif gm >= gm_min:
            components["gross_margin"] = 70
        elif gm >= gm_min * 0.7:
            components["gross_margin"] = 50
        else:
            components["gross_margin"] = 30
    else:
        components["gross_margin"] = 50

    # Debt/Equity Health
    nde = data.get("net_debt_ebitda")
    if nde is not None:
        if nde < 0:
            components["debt_health"] = 100  # net cash
        elif nde < 1.0:
            components["debt_health"] = 90
        elif nde < 2.0:
            components["debt_health"] = 70
        elif nde < 3.0:
            components["debt_health"] = 50
        else:
            components["debt_health"] = 25
    else:
        components["debt_health"] = 50

    # Revenue Growth Consistency
    rev_growth = data.get("revenue_growth")
    if rev_growth is not None:
        rev_pct = rev_growth * 100 if abs(rev_growth) < 5 else rev_growth
        if rev_pct >= 20:
            components["revenue_growth"] = 100
        elif rev_pct >= 10:
            components["revenue_growth"] = 85
        elif rev_pct >= 5:
            components["revenue_growth"] = 70
        elif rev_pct >= 0:
            components["revenue_growth"] = 50
        else:
            components["revenue_growth"] = 25
    else:
        components["revenue_growth"] = 50

    # Weighted sum
    score = sum(
        QTECH_WEIGHTS[k] * v for k, v in components.items()
    )

    return {"score": round(score, 2), "components": components}


# ─────────────────────────────────────────────
# PSOS SCORE
# ─────────────────────────────────────────────

def calc_psos(data: dict, market_ctx: dict, analyst_events: list) -> dict:
    """
    PSOS_raw = P × S × O × C (each 1–10)
    PSOS = (PSOS_raw / 10000) × 100
    """
    # ── Probability (1–10) ──
    p_components = {}
    analyst_score = _analyst_direction_score(analyst_events)
    p_components["analyst_direction"] = _scale_to_10(analyst_score, 0, 100)

    rsi = data.get("rsi", 50)
    trend_score = 10 if (data.get("above_50dma") and data.get("above_200dma")) else \
                  6 if data.get("above_200dma") else 3
    p_components["price_trend"] = trend_score

    vol_ratio = data.get("volume_ratio", 1.0) or 1.0
    p_components["volume_confirmation"] = min(10, max(1, int(vol_ratio * 5)))

    earnings_days = data.get("earnings_proximity_days")
    if earnings_days is not None and 0 <= earnings_days <= 14:
        p_components["earnings_proximity"] = 8
    elif earnings_days is not None and 15 <= earnings_days <= 30:
        p_components["earnings_proximity"] = 6
    else:
        p_components["earnings_proximity"] = 4

    p_components["options_flow"] = 5  # neutral default — no free options flow data

    P = _weighted_component(p_components, PSOS_PROBABILITY_WEIGHTS)

    # ── Severity (1–10) ──
    s_components = {}
    atr = data.get("atr", 1.0) or 1.0
    price = data.get("price", 100) or 100
    atr_pct = (atr / price) * 100
    s_components["atr_percentile"] = min(10, max(1, int(atr_pct * 2)))

    s_components["post_earnings_move"] = 5  # neutral default without historical data
    short_pct = data.get("short_percent", 0.05) or 0.05
    s_components["short_interest_pct"] = min(10, max(1, int(short_pct * 50)))
    s_components["gap_frequency"] = 5  # neutral default

    S = _weighted_component(s_components, PSOS_SEVERITY_WEIGHTS)

    # ── Opportunity (1–10) ──
    o_components = {}
    high_52 = data.get("52w_high")
    low_52 = data.get("52w_low")
    if high_52 and low_52 and price:
        range_pos = (price - low_52) / (high_52 - low_52) if high_52 != low_52 else 0.5
        o_components["upside_downside_ratio"] = max(1, min(10, int((1 - range_pos) * 10)))
    else:
        o_components["upside_downside_ratio"] = 5

    o_components["catalyst_strength"] = 5
    o_components["tam_narrative"] = 5
    o_components["valuation_rerate"] = 5

    O = _weighted_component(o_components, PSOS_OPPORTUNITY_WEIGHTS)

    # ── Signal Clarity (1–10) ──
    c_components = {}
    above_both = data.get("above_50dma") and data.get("above_200dma")
    above_one = data.get("above_200dma")
    c_components["multiframe_trend"] = 9 if above_both else 6 if above_one else 3

    rsi_val = data.get("rsi", 50) or 50
    breakout_clean = 1 if rsi_val > 70 else 0
    c_components["breakout_cleanliness"] = 8 if breakout_clean else 5

    c_components["relative_strength"] = 5  # computed vs SPY in signal confidence
    c_components["intraday_noise_penalty"] = 7  # default clean

    C = _weighted_component(c_components, PSOS_CLARITY_WEIGHTS)

    # ── Final PSOS ──
    psos_raw = P * S * O * C
    psos_normalized = round((psos_raw / 10000) * 100, 2)

    scenarios = _generate_psos_scenarios(
        p_components, s_components, o_components, c_components
    )

    return {
        "psos_raw": round(psos_raw, 2),
        "psos_normalized": psos_normalized,
        "P": round(P, 2),
        "S": round(S, 2),
        "O": round(O, 2),
        "C": round(C, 2),
        "p_components": p_components,
        "s_components": s_components,
        "o_components": o_components,
        "c_components": c_components,
        "scenarios": scenarios,
    }


# ─────────────────────────────────────────────
# SIGNAL CONFIDENCE SCORE
# ─────────────────────────────────────────────

def calc_signal_confidence(data: dict, market_ctx: dict,
                            spy_momentum: dict, analyst_events: list,
                            insider_events: list) -> dict:
    components = {}

    # RSI Strength
    rsi = data.get("rsi")
    components["rsi_strength"] = score_rsi(rsi) if rsi is not None else 50

    # Momentum — 3M + 6M relative vs SPY
    ret_3m = data.get("return_3m")
    ret_6m = data.get("return_6m")
    spy_3m = spy_momentum.get("spy_3m") or 0
    spy_6m = spy_momentum.get("spy_6m") or 0
    if ret_3m is not None and ret_6m is not None:
        rel_3m = ret_3m - spy_3m
        rel_6m = ret_6m - spy_6m
        avg_rel = (rel_3m + rel_6m) / 2
        momentum_score = min(100, max(0, 50 + avg_rel * 2))
        components["momentum"] = round(momentum_score, 1)
    else:
        components["momentum"] = 50

    # Volume Expansion
    vol_ratio = data.get("volume_ratio") or 1.0
    if vol_ratio >= 2.0:
        components["volume_expansion"] = 100
    elif vol_ratio >= 1.5:
        components["volume_expansion"] = 85
    elif vol_ratio >= 1.2:
        components["volume_expansion"] = 65
    elif vol_ratio >= 0.8:
        components["volume_expansion"] = 50
    else:
        components["volume_expansion"] = 30

    # Insider Activity
    components["insider_activity"] = _calc_insider_score(insider_events)

    # Analyst Direction
    analyst_raw = _analyst_direction_score(analyst_events)
    components["analyst_direction"] = round(analyst_raw, 1)

    # Trend Alignment — price > 50DMA > 200DMA
    above_50 = data.get("above_50dma")
    above_200 = data.get("above_200dma")
    ma50 = data.get("ma_50")
    ma200 = data.get("ma_200")
    golden_cross = (ma50 is not None and ma200 is not None and ma50 > ma200)
    if above_50 and above_200 and golden_cross:
        components["trend_alignment"] = 100
    elif above_50 and above_200:
        components["trend_alignment"] = 85
    elif above_200:
        components["trend_alignment"] = 60
    elif above_50:
        components["trend_alignment"] = 40
    else:
        components["trend_alignment"] = 20

    score = sum(
        SIGNAL_CONF_WEIGHTS[k] * v for k, v in components.items()
    )

    return {"score": round(score, 2), "components": components}


# ─────────────────────────────────────────────
# TIER CLASSIFICATION
# ─────────────────────────────────────────────

def classify_tier(score_result: dict, data: dict) -> str:
    score = score_result["omnivex_score"]
    psos_raw = score_result.get("psos_raw", 0)
    beta = data.get("beta", 1.0) or 1.0
    fcf = data.get("fcf")
    passes_gates = score_result.get("passes_smart_core_gates", False)

    # Speculative: strict requirements
    if (score >= SPECULATIVE_REQUIREMENTS["min_omnivex_score"]
            and psos_raw >= SPECULATIVE_REQUIREMENTS["min_psos_raw"]
            and beta >= SPECULATIVE_REQUIREMENTS["min_beta"]):
        return "SPECULATIVE"

    # Smart Core: quality gates + moderate score
    if passes_gates and score >= 60:
        return "SMART_CORE"

    # Tactical: momentum/catalyst driven
    if score >= 55:
        return "TACTICAL"

    return "MONITOR"


def check_smart_core_gates(data: dict) -> bool:
    """Hard gates — must ALL pass for Smart Core eligibility."""
    nde = data.get("net_debt_ebitda")
    ic = data.get("interest_coverage")
    rev_growth = data.get("revenue_growth")
    roic = data.get("roic")  # returnOnAssets proxy

    # Net Debt/EBITDA < 2x
    if nde is not None and nde > SMART_CORE_HARD_GATES["max_net_debt_ebitda"]:
        return False

    # Interest Coverage > 10x
    if ic is not None and ic < SMART_CORE_HARD_GATES["min_interest_coverage"]:
        return False

    # Revenue Growth > 5%
    if rev_growth is not None:
        rev_pct = rev_growth * 100 if abs(rev_growth) < 5 else rev_growth
        if rev_pct < SMART_CORE_HARD_GATES["min_revenue_growth_pct"]:
            return False

    # ROIC proxy (ROA) > 8% — maps to ~ROIC > 15% spec threshold
    if roic is not None and roic < SMART_CORE_HARD_GATES["min_roic_proxy"]:
        return False

    return True


# ─────────────────────────────────────────────
# FORENSIC FLAG DETECTION
# ─────────────────────────────────────────────

def _check_forensic_flags(data: dict) -> list:
    flags = []

    # 1. Earnings vs FCF mismatch
    fcf = data.get("fcf")
    earnings_growth = data.get("earnings_growth")
    rev_growth = data.get("revenue_growth")
    if fcf is not None and fcf < 0 and earnings_growth is not None and earnings_growth > 0.05:
        flags.append("FCF_EARNINGS_MISMATCH")

    # 2. Balance sheet stress — debt growing, receivables proxy
    nde = data.get("net_debt_ebitda")
    rev_g = data.get("revenue_growth") or 0
    if nde is not None and nde > 4.0 and rev_g < 0.05:
        flags.append("BALANCE_SHEET_STRESS")

    # 3. Negative FCF with no growth justification
    if fcf is not None and fcf < 0 and (rev_growth is None or rev_growth < 0.10):
        flags.append("NEGATIVE_FCF_NO_GROWTH")

    return flags


# ─────────────────────────────────────────────
# ANALYST SCORING
# ─────────────────────────────────────────────

def _analyst_direction_score(events: list) -> float:
    """
    Net analyst score from weighted events over rolling 10-day window.
    Returns 0–100 normalized.
    """
    if not events:
        return 50.0  # neutral on no data

    net = 0.0
    for event in events:
        event_score = ANALYST_EVENT_SCORES.get(event.get("event_type", ""), 0)
        source_weight = ANALYST_SOURCE_WEIGHTS.get(
            event.get("source_tier", "tier3"), 0.4
        )
        days_ago = event.get("days_ago", 10)
        recency_weight = 0.4
        for (lo, hi), w in ANALYST_RECENCY_WEIGHTS.items():
            if lo <= days_ago <= hi:
                recency_weight = w
                break
        net += event_score * source_weight * recency_weight

    # Normalize: typical range -5 to +5 → map to 0–100
    normalized = max(0, min(100, 50 + net * 10))
    return round(normalized, 2)


def _has_analyst_cluster(events: list, min_upgrades: int = 3, window_days: int = 10) -> bool:
    upgrades = sum(
        1 for e in events
        if e.get("event_type") in ("upgrade", "initiation_buy")
        and e.get("days_ago", 99) <= window_days
    )
    return upgrades >= min_upgrades


# ─────────────────────────────────────────────
# INSIDER SCORING
# ─────────────────────────────────────────────

def _calc_insider_score(events: list) -> float:
    if not events:
        return 50.0  # neutral

    qualified_titles = {"CEO", "CFO", "Chairman", "Director", "Chair"}
    total_buy_value = 0
    has_heavy_sell = False

    for e in events:
        title = e.get("title", "")
        is_qualified = any(t in title for t in qualified_titles)
        if not is_qualified:
            continue
        if e.get("is_open_market_buy") and e.get("buy_value", 0) > 0:
            total_buy_value += e.get("buy_value", 0)
        elif e.get("buy_value", 0) < -500_000:
            has_heavy_sell = True

    if has_heavy_sell and total_buy_value < 100_000:
        return float(INSIDER_HEAVY_SELL_SCORE)

    for threshold, score in sorted(INSIDER_SCORE_MAP.items(), reverse=True):
        if total_buy_value >= threshold:
            return float(score)

    return 40.0


def _has_ceo_buy(events: list) -> bool:
    return any(
        "CEO" in e.get("title", "")
        and e.get("is_open_market_buy")
        and e.get("buy_value", 0) >= 500_000
        for e in events
    )


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _weighted_component(components: dict, weights: dict) -> float:
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        if key in components:
            total += weight * components[key]
            weight_sum += weight
    if weight_sum == 0:
        return 5.0
    return total / weight_sum


def _scale_to_10(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 5.0
    scaled = (value - min_val) / (max_val - min_val) * 9 + 1
    return round(max(1, min(10, scaled)), 2)


def _is_retail_crowded(data: dict) -> bool:
    """True when institutional ownership < 50% — retail-dominated name."""
    inst = data.get("institutional_pct")
    return inst is not None and inst < 0.50


def _generate_psos_scenarios(p_components: dict, s_components: dict,
                              o_components: dict, c_components: dict) -> dict:
    """
    Derive top-2 bull and bear scenarios from PSOS sub-component scores.
    Scores are on 1–10 scale; >= 7 = meaningful signal, <= 3 = meaningful risk.
    """
    BULL_MAP = {
        ("p", "analyst_direction"):   "Analyst upgrade momentum building",
        ("p", "earnings_proximity"):  "Earnings catalyst within 30 days",
        ("p", "volume_confirmation"): "Volume expansion confirming move",
        ("o", "upside_downside_ratio"): "Price near 52W low — asymmetric upside",
        ("c", "multiframe_trend"):    "Trend confirmed above both 50/200 DMA",
        ("c", "breakout_cleanliness"): "RSI breakout — clean technical setup",
    }
    BEAR_MAP = {
        ("s", "short_interest_pct"):  "High short interest — squeeze or bearish thesis",
        ("s", "atr_percentile"):      "Elevated ATR — high gap/swing risk",
    }
    BEAR_LOW_MAP = {
        # These are bearish when their score is LOW (<=3)
        ("p", "analyst_direction"):     "Analyst downgrades — negative sentiment shift",
        ("o", "upside_downside_ratio"): "Price near 52W high — limited upside",
        ("c", "multiframe_trend"):      "Below both MAs — downtrend active",
    }

    all_scores = {
        **{("p", k): v for k, v in p_components.items()},
        **{("s", k): v for k, v in s_components.items()},
        **{("o", k): v for k, v in o_components.items()},
        **{("c", k): v for k, v in c_components.items()},
    }

    bulls = sorted(
        [(v, label) for (k, label) in BULL_MAP.items()
         if (v := all_scores.get(k, 5)) >= 7],
        reverse=True,
    )
    bears = sorted(
        [(v, label) for (k, label) in BEAR_MAP.items()
         if (v := all_scores.get(k, 5)) >= 7]
        + [(10 - v, label) for (k, label) in BEAR_LOW_MAP.items()
           if (v := all_scores.get(k, 5)) <= 3],
        reverse=True,
    )

    return {
        "bull": [label for _, label in bulls[:2]] or ["No strong upside catalysts detected"],
        "bear": [label for _, label in bears[:2]] or ["No elevated risk signals detected"],
    }
