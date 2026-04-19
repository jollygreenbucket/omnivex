"""
OMNIVEX LEGACY FUND — Core Configuration
Version: 2.3 | All values sourced directly from knowledge base
"""

# ─────────────────────────────────────────────
# UNIVERSE
# ─────────────────────────────────────────────
ETF_UNIVERSE = [
    "QQQ", "SPY", "ARKK", "VTV", "SCHD", "IJH",
    "IWM", "XLK", "XLF", "XLY", "MTUM",
    "XLV", "XLE", "XLI", "XLP", "XLU", "XLB",  # sector ETFs for overlay
    "VIXY", "SH", "PSQ",                          # anti-fund instruments
    "SGOV", "BIL",                                # cash equivalents
]

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Utilities": "XLU",
    "Materials": "XLB",
}

# ─────────────────────────────────────────────
# OMNIVEX SCORE WEIGHTS
# ─────────────────────────────────────────────
OMNIVEX_WEIGHTS = {
    "qtech": 0.40,
    "psos": 0.30,
    "signal_confidence": 0.30,
}

# ─────────────────────────────────────────────
# QTECH COMPONENT WEIGHTS
# ─────────────────────────────────────────────
QTECH_WEIGHTS = {
    "roic": 0.25,
    "peg": 0.20,
    "fcf_stability": 0.15,
    "gross_margin": 0.15,
    "debt_health": 0.10,
    "revenue_growth": 0.15,
}

# ─────────────────────────────────────────────
# SIGNAL CONFIDENCE WEIGHTS
# ─────────────────────────────────────────────
SIGNAL_CONF_WEIGHTS = {
    "rsi_strength": 0.20,
    "momentum": 0.15,
    "volume_expansion": 0.15,
    "insider_activity": 0.15,
    "analyst_direction": 0.15,
    "trend_alignment": 0.20,
}

# ─────────────────────────────────────────────
# PSOS SUBCOMPONENT WEIGHTS
# ─────────────────────────────────────────────
PSOS_PROBABILITY_WEIGHTS = {
    "analyst_direction": 0.30,
    "price_trend": 0.25,
    "volume_confirmation": 0.20,
    "earnings_proximity": 0.15,
    "options_flow": 0.10,
}

PSOS_SEVERITY_WEIGHTS = {
    "atr_percentile": 0.40,
    "post_earnings_move": 0.30,
    "short_interest_pct": 0.20,
    "gap_frequency": 0.10,
}

PSOS_OPPORTUNITY_WEIGHTS = {
    "upside_downside_ratio": 0.35,
    "catalyst_strength": 0.25,
    "tam_narrative": 0.20,
    "valuation_rerate": 0.20,
}

PSOS_CLARITY_WEIGHTS = {
    "multiframe_trend": 0.40,
    "breakout_cleanliness": 0.30,
    "relative_strength": 0.20,
    "intraday_noise_penalty": 0.10,
}

# ─────────────────────────────────────────────
# SCORE INTERPRETATION
# ─────────────────────────────────────────────
SCORE_THRESHOLDS = {
    "breakout": 80,
    "overweight": 70,
    "maintain": 60,
    "underweight": 50,
    "exclude": 0,
}

def interpret_score(score):
    if score >= 80:
        return "BREAKOUT"
    elif score >= 70:
        return "OVERWEIGHT"
    elif score >= 60:
        return "MAINTAIN"
    elif score >= 50:
        return "UNDERWEIGHT"
    else:
        return "EXCLUDE"

def recommend_action(score, current_tier, has_position):
    if score >= 80:
        return "BUY" if not has_position else "ADD"
    elif score >= 70:
        return "ADD" if has_position else "MONITOR"
    elif score >= 60:
        return "HOLD" if has_position else "MONITOR"
    elif score >= 50:
        return "REDUCE" if has_position else "MONITOR"
    else:
        return "REMOVE" if has_position else "EXCLUDE"

# ─────────────────────────────────────────────
# SCORE ADJUSTMENTS
# ─────────────────────────────────────────────
SCORE_ADJUSTMENTS = {
    "analyst_upgrade_cluster": +2,
    "ceo_insider_buy": +3,
    "retail_crowding": -5,
    "forensic_red_flag": -15,
}

# ─────────────────────────────────────────────
# MODE DETECTION THRESHOLDS
# ─────────────────────────────────────────────
ALPHA_THRESHOLDS = {
    "vix_max": 18,
    "ad_ratio_min": 1.3,
    "rsi_breakout_min_tickers": 3,
    "rsi_breakout_level": 70,
    "arkk_move_min_pct": 2.0,
    "triggers_required": 4,
    "total_triggers": 6,
}

HEDGE_THRESHOLDS = {
    "vix_min": 22,
    "ad_ratio_max": 0.8,
    "low_score_ticker_count": 10,
    "low_score_threshold": 50,
    "bearish_high_confidence_count": 5,
    "triggers_required": 3,
    "total_triggers": 5,
}

CHOP_GUARD = {
    "atr_compression_days": 20,  # 20-day low ATR
    "speculative_cap_pct": 0.10,
}

AD_SMOOTHING_DAYS = 3

# ─────────────────────────────────────────────
# TIER ALLOCATION RULES
# ─────────────────────────────────────────────
TIER_ALLOCATION = {
    "CORE": {
        "smart_core": (0.45, 0.60),
        "tactical": (0.20, 0.30),
        "speculative": (0.05, 0.10),
        "cash": (0.10, 0.25),
        "hedge": (0.00, 0.05),
    },
    "ALPHA": {
        "smart_core": (0.30, 0.40),
        "tactical": (0.40, 0.50),
        "speculative": (0.10, 0.20),
        "cash": (0.00, 0.10),
        "hedge": (0.00, 0.00),
    },
    "HEDGE": {
        "smart_core": (0.10, 0.20),
        "tactical": (0.00, 0.05),
        "speculative": (0.00, 0.00),
        "cash": (0.30, 0.30),
        "inverse_etf": (0.30, 0.30),
        "volatility": (0.20, 0.20),
    },
}

POSITION_SIZING = {
    "smart_core": {"base": (0.04, 0.06), "max": 0.08, "score_bonus_threshold": 75},
    "tactical":   {"base": (0.03, 0.05), "max": 0.07, "score_bonus_threshold": 75},
    "speculative":{"base": (0.01, 0.02), "max": 0.03, "score_bonus_threshold": 80},
}

RISK_CONTROLS = {
    "max_single_name_pct": 0.08,
    "max_sector_pct": 0.25,
    "stop_loss_tactical": -0.12,
    "stop_loss_speculative": -0.15,
    "trailing_stop_min": 0.10,
    "trailing_stop_max": 0.20,
    "neutral_min_cash": 0.10,
}

# ─────────────────────────────────────────────
# SPECULATIVE HARD REQUIREMENTS
# ─────────────────────────────────────────────
SPECULATIVE_REQUIREMENTS = {
    "min_omnivex_score": 80,
    "min_psos_raw": 1500,   # PRE-NORMALIZATION — not the 0-100 normalized value
    "min_beta": 1.5,
}

# ─────────────────────────────────────────────
# SMART CORE SCREENING — HARD GATES
# ─────────────────────────────────────────────
SMART_CORE_HARD_GATES = {
    "max_net_debt_ebitda": 2.0,
    "min_interest_coverage": 10.0,
    "min_revenue_growth_pct": 5.0,
}

# ─────────────────────────────────────────────
# SECTOR-ADJUSTED SCREENING THRESHOLDS
# ─────────────────────────────────────────────
SECTOR_THRESHOLDS = {
    "Technology":             {"gross_margin_min": 0.40, "pe_max": 30, "fcf_yield_min": 0.02},
    "Healthcare":             {"gross_margin_min": 0.35, "pe_max": 28, "fcf_yield_min": 0.02},
    "Financials":             {"gross_margin_min": None, "pe_max": 18, "fcf_yield_min": None, "roe_min": 0.15},
    "Industrials":            {"gross_margin_min": 0.25, "pe_max": 22, "fcf_yield_min": 0.03},
    "Consumer Staples":       {"gross_margin_min": 0.30, "pe_max": 22, "fcf_yield_min": 0.03},
    "Consumer Discretionary": {"gross_margin_min": 0.30, "pe_max": 22, "fcf_yield_min": 0.03},
    "Energy":                 {"gross_margin_min": 0.20, "pe_max": 15, "fcf_yield_min": 0.04},
    "Utilities":              {"gross_margin_min": 0.25, "pe_max": 20, "fcf_yield_min": 0.03},
    "Materials":              {"gross_margin_min": 0.25, "pe_max": 20, "fcf_yield_min": 0.03},
    "default":                {"gross_margin_min": 0.40, "pe_max": 25, "fcf_yield_min": 0.03},
}

# ─────────────────────────────────────────────
# SMART CORE SECTOR CORE WEIGHTS
# ─────────────────────────────────────────────
SECTOR_CORE_WEIGHTS = {
    "Technology": 0.20,
    "Financials": 0.15,
    "Healthcare": 0.15,
    "Consumer Staples": 0.10,
    "Energy": 0.10,
    "Industrials": 0.10,
    "Consumer Discretionary": 0.10,
    "Utilities": 0.05,
    "Materials": 0.05,
}

# ─────────────────────────────────────────────
# ANALYST SCORING
# ─────────────────────────────────────────────
ANALYST_EVENT_SCORES = {
    "upgrade": 1.0,
    "pt_raise": 0.5,
    "downgrade": -1.0,
    "pt_cut": -0.5,
    "initiation_buy": 0.75,
    "initiation_sell": -0.75,
}

ANALYST_SOURCE_WEIGHTS = {
    "tier1": 1.0,
    "tier2": 0.7,
    "tier3": 0.4,
}

ANALYST_RECENCY_WEIGHTS = {
    (0, 2): 1.0,
    (3, 5): 0.7,
    (6, 10): 0.4,
}

ANALYST_WINDOW_DAYS = 10

# ─────────────────────────────────────────────
# INSIDER SCORING
# ─────────────────────────────────────────────
INSIDER_SCORE_MAP = {
    1_000_000: 100,
    500_000: 85,
    100_000: 65,
    0: 40,
}
INSIDER_HEAVY_SELL_SCORE = 20
INSIDER_LOOKBACK_DAYS = 30
INSIDER_QUALIFIED_TITLES = ["CEO", "CFO", "Chairman", "Director", "Chair"]

# ─────────────────────────────────────────────
# RSI SCORING
# ─────────────────────────────────────────────
RSI_SCORE_MAP = [
    (80, 101, 70),   # exhaustion
    (70, 80, 90),    # breakout
    (60, 70, 75),    # bullish
    (50, 60, 50),    # neutral
    (0, 50, 25),     # weak
]

def score_rsi(rsi):
    for low, high, score in RSI_SCORE_MAP:
        if low <= rsi < high:
            return score
    return 25

# ─────────────────────────────────────────────
# EXECUTION CONTROL
# ─────────────────────────────────────────────
EXECUTION_STAGE = 1  # 1=recommendations only, 2=human-approved, 3=semi-auto, 4=full-auto

HUMAN_REVIEW_TRIGGERS = {
    "signal_confidence_min": 60,
    "overnight_gap_max_pct": 4.0,
    "spread_max_bps": 35,
}

STAGE2_ACTIONS = {"BUY", "ADD", "REDUCE", "REMOVE", "ROTATE", "HEDGE"}
STAGE3_AUTO_ACTIONS = {"HOLD", "MONITOR"}

ROTATE_FILL_THRESHOLD = 0.90  # confirm >= 90% fill on sell leg before placing buy

# ─────────────────────────────────────────────
# OUTPUT PATHS
# ─────────────────────────────────────────────
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

TODAY = date.today().isoformat()
CSV_PATH = os.path.join(LOG_DIR, f"omnivex_audit_{TODAY}.csv")
HTML_PATH = os.path.join(REPORT_DIR, f"omnivex_report_{TODAY}.html")
