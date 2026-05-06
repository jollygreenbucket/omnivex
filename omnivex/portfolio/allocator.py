"""
OMNIVEX — Portfolio Construction Layer

Converts scored names into a target portfolio and rebalance plan that
respects mode sleeves, tier sizing, single-name caps, sector caps, and cash.
"""

from __future__ import annotations

import math
from collections import defaultdict

from core.config import POSITION_SIZING, RISK_CONTROLS
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


def _midpoint(bounds: tuple[float, float]) -> float:
    return round(((bounds[0] + bounds[1]) / 2) * 100, 2)


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


def _candidate_seed_weight(score: dict, sleeve: str) -> float:
    sizing = POSITION_SIZING[sleeve]
    base_low = sizing["base"][0] * 100
    suggested = float(score.get("suggested_weight_pct") or 0.0)
    return round(max(base_low, suggested), 2)


def _build_target_sleeves(mode_result: dict) -> tuple[dict[str, float], list[str]]:
    raw_alloc = get_target_allocation(mode_result)
    notes = []
    sleeves = {}
    overflow_to_cash = 0.0

    for key, value in raw_alloc.items():
        if key == "chop_guard_note":
            notes.append(str(value))
            continue
        if not isinstance(value, tuple):
            continue
        midpoint_pct = _midpoint(value)
        if key in SLEEVE_ORDER or key == "cash":
            sleeves[key] = midpoint_pct
        else:
            overflow_to_cash += midpoint_pct
            notes.append(f"{key} sleeve parked in cash pending implementation")

    sleeves["cash"] = round(sleeves.get("cash", 0.0) + overflow_to_cash, 2)
    return sleeves, notes


def build_target_portfolio(
    mode_result: dict,
    scored: list[dict],
    holdings: list[dict] | None = None,
    total_portfolio_value: float | None = None,
    cash: float | None = None,
) -> dict:
    holdings_by_ticker = _holding_map(holdings)
    current_cash = float(cash or 0.0)
    current_total_value = float(total_portfolio_value or 0.0)

    target_sleeves, notes = _build_target_sleeves(mode_result)
    sector_cap_pct = float(RISK_CONTROLS["max_sector_pct"] * 100)
    single_name_cap_pct = float(RISK_CONTROLS["max_single_name_pct"] * 100)

    required_positions = 0
    for sleeve in SLEEVE_ORDER:
        target_pct = target_sleeves.get(sleeve, 0.0)
        if target_pct <= 0:
            continue
        tier_cap_pct = min(single_name_cap_pct, POSITION_SIZING[sleeve]["max"] * 100)
        required_positions += math.ceil(target_pct / tier_cap_pct)
    max_positions = max(12, required_positions)

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
        row["seed_weight_pct"] = _candidate_seed_weight(score, sleeve)
        candidates_by_sleeve[sleeve].append(row)

    for sleeve in candidates_by_sleeve:
        candidates_by_sleeve[sleeve].sort(
            key=lambda row: (
                -(float(row.get("omnivex_score") or 0.0)),
                -(float(row.get("suggested_weight_pct") or 0.0)),
                row.get("ticker") or "",
            )
        )

    sector_totals: dict[str, float] = defaultdict(float)
    target_rows: dict[str, dict] = {}
    allocated_cash_pct = 0.0
    total_positions = 0

    for sleeve in SLEEVE_ORDER:
        target_pct = target_sleeves.get(sleeve, 0.0)
        if target_pct <= 0:
            continue

        tier = SLEEVE_TO_TIER[sleeve]
        tier_cap_pct = min(single_name_cap_pct, POSITION_SIZING[sleeve]["max"] * 100)
        tier_min_pct = POSITION_SIZING[sleeve]["base"][0] * 100
        remaining = target_pct
        selected: list[str] = []

        for candidate in candidates_by_sleeve.get(sleeve, []):
            if remaining <= 0.01:
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

            seed = min(candidate["seed_weight_pct"], tier_cap_pct)
            assigned = min(seed, tier_cap_pct, sector_room, remaining)
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
                "reason": f"{tier} sleeve seed fill",
                "flags": "|".join(sorted(_split_flags(candidate.get("flags")))),
            }
            selected.append(ticker)
            sector_totals[sector] += assigned
            total_positions += 1
            remaining -= assigned

        # Top up existing selected names until sleeve target or caps are hit.
        progress = True
        while remaining > 0.01 and progress:
            progress = False
            for ticker in selected:
                row = target_rows[ticker]
                sector = row["sector"]
                room = tier_cap_pct - row["target_weight_pct"]
                sector_room = max(0.0, sector_cap_pct - sector_totals[sector])
                increment = min(room, sector_room, remaining)
                if increment <= 0.01:
                    continue
                row["target_weight_pct"] = round(row["target_weight_pct"] + increment, 2)
                row["reason"] = f"{tier} sleeve top-up"
                sector_totals[sector] += increment
                remaining -= increment
                progress = True

        allocated_cash_pct += max(0.0, remaining)

    target_cash_pct = round(target_sleeves.get("cash", 0.0) + allocated_cash_pct, 2)
    target_invested_pct = round(sum(row["target_weight_pct"] for row in target_rows.values()), 2)

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
            rec_reason = "New entrant"
        elif abs(delta_weight_pct) < MIN_REBALANCE_DELTA_PCT and abs(delta_value) < MIN_REBALANCE_DELTA_DOLLARS:
            recommendation = "HOLD"
            rec_reason = "Inside rebalance threshold"
        elif delta_weight_pct > 0:
            recommendation = "ADD"
            rec_reason = "Below target weight"
        else:
            recommendation = "TRIM"
            rec_reason = "Above target weight"

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

    all_rows.sort(key=lambda row: ({"OPEN": 0, "ADD": 1, "TRIM": 2, "EXIT": 3, "HOLD": 4}.get(row["recommendation"], 9), -abs(row["delta_value"])))

    estimated_turnover_pct = round(sum(abs(row["delta_weight_pct"]) for row in all_rows) / 2, 2)

    return {
        "mode": mode_result.get("mode"),
        "portfolio_base_value": round(portfolio_base_value, 2),
        "cash": round(current_cash, 2),
        "max_positions": max_positions,
        "notes": notes,
        "target_sleeves": {
            "SMART_CORE": round(target_sleeves.get("smart_core", 0.0), 2),
            "TACTICAL": round(target_sleeves.get("tactical", 0.0), 2),
            "SPECULATIVE": round(target_sleeves.get("speculative", 0.0), 2),
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
