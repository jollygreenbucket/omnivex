"""Strategy metadata and persisted config snapshots for Omnivex."""

from __future__ import annotations

from copy import deepcopy

from core.config import CHOP_GUARD, POSITION_SIZING, RISK_CONTROLS, TIER_ALLOCATION

STRATEGY_VERSION = "allocator-v1"

ALLOCATOR_RULES = {
    "eligible_actions": ["BUY", "ADD", "HOLD"],
    "min_rebalance_delta_pct": 1.5,
    "min_rebalance_delta_dollars": 250.0,
    "block_new_buys_within_earnings_days": 7,
    "allocation_method": "mode_midpoint_then_tier_fill",
    "cash_policy": "residual_to_cash",
}

BACKTEST_BASELINE = {
    "name": "Omnivex Baseline v1",
    "selection": "top_10_buy_add",
    "weighting": "equal",
    "execution": "next_session_proxy",
    "slippage_bps_per_side": 10,
    "benchmark": "SPY",
}


def build_strategy_snapshot() -> dict:
    return {
        "version": STRATEGY_VERSION,
        "allocator_rules": deepcopy(ALLOCATOR_RULES),
        "tier_allocation": deepcopy(TIER_ALLOCATION),
        "position_sizing": deepcopy(POSITION_SIZING),
        "risk_controls": deepcopy(RISK_CONTROLS),
        "chop_guard": deepcopy(CHOP_GUARD),
        "backtest_baseline": deepcopy(BACKTEST_BASELINE),
    }
