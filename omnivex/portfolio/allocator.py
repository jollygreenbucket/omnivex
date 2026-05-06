"""
OMNIVEX — Portfolio Construction Layer

Allocator v2 treats mode sleeve ranges as ceiling budgets rather than fill
quotas. Capital is deployed only into qualified opportunities, with staged
position sizing and signal persistence for durable sleeves like SMART_CORE.
"""

from __future__ import annotations

import math
from collections import defaultdict

from core.config import ALLOCATOR_THRESHOLDS, POSITION_SIZING, RISK_CONTROLS
from core.mode_detector import get_target_allocation

SLEEVE_ORDER = ("smart_core", "tactical", "speculative")
TIER_TO_SLEEVE = {
    "SMART_CORE": "smart_core",
    "TACTICAL": "tactical",
    "SPECULATIVE": "speculative",
}
SLEEVE_TO_TIER = {value: key for key, value in TIER_TO_SLEEVE.items()}
ELIGIBLE_ACTIONS = {"BUY", "ADD", "HOLD"}
MIN_REBALANCE_DELTA_PCT = 1.5
MIN_REBALANCE_DELTA_DOLLARS = 250.0


def _lower_pct(bounds: tuple[float, float]) -> float:
    return round(bounds[0] * 100, 2)


def _upper_pct(bounds: tuple[float, float]) -> float:
    return round(bounds[1] * 100, 2)


def _holding_map(holdings: list[dict] | None) -> dict[str, dict]:
    if not holdings:
        return {}
    return {str(holding.get("ticker")): holding for holding in holdings if holding.get("ticker")}


def _split_flags(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {flag for flag in value.split("|") if flag}
    return {str(flag) for flag in value if flag}


def _build_budget_sleeves(mode_result: dict) -> tuple[dict[str, float], float, float, list[str]]:
    raw_alloc = get_target_allocation(mode_result)
    notes = []
    ceilings: dict[str, float] = {}
    cash_floor_pct = 0.0
    parked_cash_pct = 0.0

    for key, value in raw_alloc.items():
        if key == "chop_guard_note":
            notes.append(str(value))
            continue
        if not isinstance(value, tuple):
            continue
        if key == "cash":
            cash_floor_pct = _lower_pct(value)
        elif key in SLEEVE_ORDER:
            ceilings[key] = _upper_pct(value)
        elif key in {"inverse_etf", "volatility"}:
            parked_cash_pct += _upper_pct(value)
            notes.append(f"{key} sleeve parked in cash pending implementation")
        elif key == "hedge":
            if mode_result.get("mode") == "HEDGE":
                parked_cash_pct += _upper_pct(value)
                notes.append("hedge sleeve parked in cash pending implementation")
            else:
                notes.append("optional hedge sleeve excluded from long-only allocator")

    return ceilings, cash_floor_pct, parked_cash_pct, notes


def _candidate_sort_key(row: dict) -> tuple:
    stage_rank = {"breakout": 0, "confirmed": 1, "starter": 2}.get(row["stage"], 9)
    return (
        stage_rank,
        -(float(row.get("qualifying_runs") or 0.0)),
        -(float(row.get("omnivex_score") or 0.0)),
        -(float(row.get("suggested_weight_pct") or 0.0)),
        row.get("ticker") or "",
    )


def _history_streak(history_rows: list[dict], sleeve: str) -> int:
    threshold = ALLOCATOR_THRESHOLDS[sleeve]["starter_score"]
    streak = 0
    for row in history_rows:
        if TIER_TO_SLEEVE.get(row.get("tier")) != sleeve:
            break
        if row.get("action") not in ELIGIBLE_ACTIONS:
            break
        if float(row.get("omnivex_score") or 0.0) < threshold:
            break
        streak += 1
    return streak


def _candidate_stage(score: dict, sleeve: str, history_rows: list[dict]) -> dict:
    sizing = POSITION_SIZING[sleeve]
    thresholds = ALLOCATOR_THRESHOLDS[sleeve]
    score_value = float(score.get("omnivex_score") or 0.0)
    base_low = sizing["base"][0] * 100
    base_high = sizing["base"][1] * 100
    cap = min(RISK_CONTROLS["max_single_name_pct"] * 100, sizing["max"] * 100)
    suggested = float(score.get("suggested_weight_pct") or 0.0)
    anchor = max(base_high, suggested)
    qualifying_runs = _history_streak(history_rows, sleeve) + 1

    if score_value < thresholds["starter_score"]:
        return {}

    if sleeve == "smart_core":
        confirmed = qualifying_runs >= thresholds["persistence_runs"] and score_value >= thresholds["full_score"]
        stage = "confirmed" if confirmed else "starter"
        multiplier = thresholds["confirmed_multiplier"] if confirmed else thresholds["starter_multiplier"]
    elif sleeve == "tactical":
        if score_value >= thresholds["full_score"]:
            stage = "breakout"
            multiplier = thresholds["breakout_multiplier"]
        elif qualifying_runs >= thresholds["persistence_runs"]:
            stage = "confirmed"
            multiplier = thresholds["confirmed_multiplier"]
        else:
            stage = "starter"
            multiplier = thresholds["starter_multiplier"]
    else:
        stage = "breakout"
        multiplier = thresholds["confirmed_multiplier"]

    target = min(cap, max(base_low, anchor * multiplier))
    if stage == "starter":
        topup_cap = target
    elif stage == "confirmed":
        topup_cap = min(cap, max(target, anchor))
    else:
        topup_cap = cap

    return {
        "stage": stage,
        "qualifying_runs": qualifying_runs,
        "desired_weight_pct": round(target, 2),
        "topup_cap_pct": round(topup_cap, 2),
    }


def build_target_portfolio(
    mode_result: dict,
    scored: list[dict],
    holdings: list[dict] | None = None,
    total_portfolio_value: float | None = None,
    cash: float | None = None,
    signal_history: dict[str, list[dict]] | None = None,
) -> dict:
    holdings_by_ticker = _holding_map(holdings)
    history_map = signal_history or {}
    current_cash = float(cash or 0.0)
    current_total_value = float(total_portfolio_value or 0.0)

    sleeve_ceilings, cash_floor_pct, parked_cash_pct, notes = _build_budget_sleeves(mode_result)
    sector_cap_pct = float(RISK_CONTROLS["max_sector_pct"] * 100)
    single_name_cap_pct = float(RISK_CONTROLS["max_single_name_pct"] * 100)

    required_positions = 0
    for sleeve in SLEEVE_ORDER:
        ceiling_pct = sleeve_ceilings.get(sleeve, 0.0)
        if ceiling_pct <= 0:
            continue
        tier_cap_pct = min(single_name_cap_pct, POSITION_SIZING[sleeve]["max"] * 100)
        required_positions += math.ceil(ceiling_pct / tier_cap_pct)
    max_positions = max(10, required_positions)

    notes.append(
        "allocator-v2: sleeve ceilings apply only to qualified opportunities; residual stays cash"
    )

    candidates_by_sleeve: dict[str, list[dict]] = defaultdict(list)
    blocked: list[dict] = []
    for score in scored:
        ticker = score.get("ticker")
        tier = score.get("tier")
        sleeve = TIER_TO_SLEEVE.get(tier)
        held = ticker in holdings_by_ticker
        flags = _split_flags(score.get("flags"))

        reasons = []
        if not sleeve:
            reasons.append("Tier not allocatable")
        if score.get("action") not in ELIGIBLE_ACTIONS:
            reasons.append("Action not eligible")
        if "FORENSIC" in flags:
            reasons.append("Forensic flag")
        if score.get("data_quality") == "MISSING":
            reasons.append("Missing data")
        if not held and "EARNINGS_IMMINENT" in flags:
            reasons.append("Earnings inside 7-day window")

        stage_info = {}
        if sleeve and not reasons:
            stage_info = _candidate_stage(score, sleeve, history_map.get(str(ticker), []))
            if not stage_info:
                reasons.append(f"Below {sleeve} entry threshold")

        if reasons:
            if held or sleeve:
                blocked.append(
                    {
                        "ticker": ticker,
                        "tier": tier,
                        "sleeve": sleeve,
                        "held": held,
                        "reason": "; ".join(reasons),
                        "action": score.get("action"),
                    }
                )
            continue

        row = dict(score)
        row["held"] = held
        row["sleeve"] = sleeve
        row.update(stage_info)
        candidates_by_sleeve[sleeve].append(row)

    for sleeve in candidates_by_sleeve:
        candidates_by_sleeve[sleeve].sort(key=_candidate_sort_key)

    sector_totals: dict[str, float] = defaultdict(float)
    sleeve_totals: dict[str, float] = defaultdict(float)
    target_rows: dict[str, dict] = {}
    total_positions = 0

    for sleeve in SLEEVE_ORDER:
        ceiling_pct = sleeve_ceilings.get(sleeve, 0.0)
        if ceiling_pct <= 0:
            continue

        tier = SLEEVE_TO_TIER[sleeve]
        tier_cap_pct = min(single_name_cap_pct, POSITION_SIZING[sleeve]["max"] * 100)
        tier_min_pct = POSITION_SIZING[sleeve]["base"][0] * 100
        selected: list[str] = []

        for candidate in candidates_by_sleeve.get(sleeve, []):
            remaining_budget = ceiling_pct - sleeve_totals[sleeve]
            if remaining_budget <= 0.01:
                break
            ticker = candidate["ticker"]
            if ticker in target_rows:
                continue
            if total_positions >= max_positions and not candidate["held"]:
                break

            sector = candidate.get("sector") or "Unknown"
            sector_room = max(0.0, sector_cap_pct - sector_totals[sector])
            if sector_room <= 0.01:
                continue

            assigned = min(candidate["desired_weight_pct"], tier_cap_pct, sector_room, remaining_budget)
            if not candidate["held"] and assigned + 1e-9 < tier_min_pct:
                continue

            target_rows[ticker] = {
                "ticker": ticker,
                "sector": sector,
                "tier": tier,
                "sleeve": sleeve,
                "rank_in_sleeve": len(selected) + 1,
                "action": candidate.get("action"),
                "omnivex_score": float(candidate.get("omnivex_score") or 0.0),
                "signal_conf": float(candidate.get("signal_confidence") or 0.0),
                "suggested_weight_pct": float(candidate.get("suggested_weight_pct") or 0.0),
                "target_weight_pct": round(assigned, 2),
                "held": candidate["held"],
                "reason": (
                    f"{tier} {candidate['stage']} allocation "
                    f"({candidate['qualifying_runs']} qualifying runs)"
                ),
                "flags": "|".join(sorted(_split_flags(candidate.get("flags")))),
                "stage": candidate["stage"],
                "qualifying_runs": candidate["qualifying_runs"],
                "topup_cap_pct": candidate["topup_cap_pct"],
            }
            selected.append(ticker)
            sector_totals[sector] += assigned
            sleeve_totals[sleeve] += assigned
            total_positions += 1

        progress = True
        while progress and sleeve_totals[sleeve] + 0.01 < ceiling_pct:
            progress = False
            for ticker in selected:
                row = target_rows[ticker]
                sector = row["sector"]
                row_cap = min(tier_cap_pct, row.get("topup_cap_pct", row["target_weight_pct"]))
                row_room = max(0.0, row_cap - row["target_weight_pct"])
                remaining_budget = max(0.0, ceiling_pct - sleeve_totals[sleeve])
                sector_room = max(0.0, sector_cap_pct - sector_totals[sector])
                increment = min(row_room, remaining_budget, sector_room)
                if increment <= 0.01:
                    continue
                row["target_weight_pct"] = round(row["target_weight_pct"] + increment, 2)
                row["reason"] = (
                    f"{row['tier']} {row['stage']} top-up "
                    f"({row['qualifying_runs']} qualifying runs)"
                )
                sector_totals[sector] += increment
                sleeve_totals[sleeve] += increment
                progress = True

    actual_sleeves = {
        "SMART_CORE": round(sleeve_totals.get("smart_core", 0.0), 2),
        "TACTICAL": round(sleeve_totals.get("tactical", 0.0), 2),
        "SPECULATIVE": round(sleeve_totals.get("speculative", 0.0), 2),
    }

    target_invested_pct = round(sum(actual_sleeves.values()), 2)
    target_cash_pct = round(max(cash_floor_pct + parked_cash_pct, 100.0 - target_invested_pct), 2)
    notes.append(
        f"cash floor {cash_floor_pct:.1f}% with sleeve ceilings "
        f"{actual_sleeves['SMART_CORE']:.1f}/{actual_sleeves['TACTICAL']:.1f}/{actual_sleeves['SPECULATIVE']:.1f}"
    )

    current_long_value = sum(float(holding.get("market_value") or 0.0) for holding in holdings_by_ticker.values())
    portfolio_base_value = current_total_value or (current_long_value + current_cash)

    current_sleeves = defaultdict(float)
    if portfolio_base_value > 0:
        for holding in holdings_by_ticker.values():
            tier = str(holding.get("tier") or "UNASSIGNED")
            sleeve = TIER_TO_SLEEVE.get(tier)
            if sleeve:
                current_sleeves[sleeve] += (float(holding.get("market_value") or 0.0) / portfolio_base_value) * 100
        current_sleeves["cash"] = (current_cash / portfolio_base_value) * 100 if current_cash else 0.0

    all_rows: list[dict] = []
    seen = set()
    for ticker, target in target_rows.items():
        holding = holdings_by_ticker.get(ticker)
        current_value = float(holding.get("market_value") or 0.0) if holding else 0.0
        current_weight_pct = (current_value / portfolio_base_value) * 100 if portfolio_base_value > 0 else 0.0
        target_value = portfolio_base_value * (target["target_weight_pct"] / 100) if portfolio_base_value > 0 else 0.0
        delta_value = target_value - current_value
        delta_weight_pct = target["target_weight_pct"] - current_weight_pct

        if not holding:
            recommendation = "OPEN"
            rec_reason = target["reason"]
        elif abs(delta_weight_pct) < MIN_REBALANCE_DELTA_PCT and abs(delta_value) < MIN_REBALANCE_DELTA_DOLLARS:
            recommendation = "HOLD"
            rec_reason = "Inside rebalance threshold"
        elif delta_weight_pct > 0:
            recommendation = "ADD"
            rec_reason = target["reason"]
        else:
            recommendation = "TRIM"
            rec_reason = "Above staged target"

        all_rows.append(
            {
                **target,
                "current_value": round(current_value, 2),
                "current_weight_pct": round(current_weight_pct, 2),
                "target_value": round(target_value, 2),
                "delta_value": round(delta_value, 2),
                "delta_weight_pct": round(delta_weight_pct, 2),
                "recommendation": recommendation,
                "recommendation_reason": rec_reason,
                "shares": float(holding.get("shares") or 0.0) if holding else 0.0,
                "current_price": float(holding.get("current_price") or 0.0) if holding else 0.0,
                "market_value": round(current_value, 2),
            }
        )
        seen.add(ticker)

    for ticker, holding in holdings_by_ticker.items():
        if ticker in seen:
            continue
        current_value = float(holding.get("market_value") or 0.0)
        current_weight_pct = (current_value / portfolio_base_value) * 100 if portfolio_base_value > 0 else 0.0
        blocked_row = next((row for row in blocked if row["ticker"] == ticker), None)
        all_rows.append(
            {
                "ticker": ticker,
                "sector": None,
                "tier": str(holding.get("tier") or "UNASSIGNED"),
                "sleeve": blocked_row.get("sleeve") if blocked_row else None,
                "rank_in_sleeve": None,
                "action": blocked_row.get("action") if blocked_row else "REVIEW",
                "omnivex_score": None,
                "signal_conf": None,
                "suggested_weight_pct": 0.0,
                "target_weight_pct": 0.0,
                "held": True,
                "reason": "No longer eligible for target book",
                "flags": "",
                "stage": None,
                "qualifying_runs": None,
                "current_value": round(current_value, 2),
                "current_weight_pct": round(current_weight_pct, 2),
                "target_value": 0.0,
                "delta_value": round(-current_value, 2),
                "delta_weight_pct": round(-current_weight_pct, 2),
                "recommendation": "EXIT",
                "recommendation_reason": blocked_row["reason"] if blocked_row else "Not in allocator target set",
                "shares": float(holding.get("shares") or 0.0),
                "current_price": float(holding.get("current_price") or 0.0),
                "market_value": round(current_value, 2),
            }
        )

    all_rows.sort(
        key=lambda row: (
            {"OPEN": 0, "ADD": 1, "TRIM": 2, "EXIT": 3, "HOLD": 4}.get(row["recommendation"], 9),
            -abs(row["delta_value"]),
        )
    )

    estimated_turnover_pct = round(sum(abs(row["delta_weight_pct"]) for row in all_rows) / 2, 2)

    return {
        "mode": mode_result.get("mode"),
        "portfolio_base_value": round(portfolio_base_value, 2),
        "cash": round(current_cash, 2),
        "max_positions": max_positions,
        "notes": notes,
        "target_sleeves": {
            **actual_sleeves,
            "CASH": target_cash_pct,
        },
        "current_sleeves": {
            "SMART_CORE": round(current_sleeves.get("smart_core", 0.0), 2),
            "TACTICAL": round(current_sleeves.get("tactical", 0.0), 2),
            "SPECULATIVE": round(current_sleeves.get("speculative", 0.0), 2),
            "CASH": round(current_sleeves.get("cash", 0.0), 2),
        },
        "target_invested_pct": target_invested_pct,
        "target_cash_pct": target_cash_pct,
        "estimated_turnover_pct": estimated_turnover_pct,
        "rows": all_rows,
    }
