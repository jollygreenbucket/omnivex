"""
OMNIVEX — Historical Research Repository Runner

Backfills synthetic historical Omnivex runs into dedicated research tables and
writes a local price cache for inspection.
"""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from research.historical_repository import (
    HistoricalRepositoryConfig,
    build_historical_repository,
    persist_historical_repository,
)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Omnivex historical research repository")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--frequency", default="W-FRI", help="Pandas resample frequency (default: W-FRI)")
    parser.add_argument("--max-tickers", type=int, default=75, help="Max universe size")
    parser.add_argument("--universe-name", default="current_static", help="Research universe label")
    parser.add_argument("--no-db-universe", action="store_true", help="Build the universe from current ETF scan instead of DB scores")
    parser.add_argument("--no-persist", action="store_true", help="Build repository without writing to Postgres")
    args = parser.parse_args()

    config = HistoricalRepositoryConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        frequency=args.frequency,
        universe_name=args.universe_name,
        max_tickers=args.max_tickers,
        use_db_universe=not args.no_db_universe,
    )

    result = build_historical_repository(config)
    if not args.no_persist:
        persist_historical_repository(result)

    print("\nOMNIVEX HISTORICAL RESEARCH REPOSITORY")
    print(f"  Universe:      {len(result['universe'])} tickers")
    print(f"  Run dates:     {len(result['runs'])}")
    print(f"  Frequency:     {config.frequency}")
    print(f"  Cache:         {result['cache_dir']}")
    print(f"  Persisted:     {'no' if args.no_persist else 'yes'}")
    if result["runs"]:
        latest = result["runs"][-1]
        print(f"  Latest run:    {latest['as_of_date']} ({latest['mode']})")
        print(f"  Tickers scored:{latest['ticker_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
