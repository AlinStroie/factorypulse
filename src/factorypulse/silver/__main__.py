"""Rulare: python -m factorypulse.silver [--from AAAA-LL-ZZ] [--to AAAA-LL-ZZ]

Implicit reconstruieste ieri si azi (UTC). Caile vin din BRONZE_DIR si SILVER_DIR.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from factorypulse.silver.build import build


def main(argv: list[str] | None = None) -> int:
    today = datetime.now(UTC).date()
    parser = argparse.ArgumentParser(description="Construieste silver din bronze.")
    parser.add_argument("--from", dest="first", type=date.fromisoformat, default=None)
    parser.add_argument("--to", dest="last", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    last: date = args.last or today
    first: date = args.first or (last - timedelta(days=1))
    if first > last:
        parser.error("--from e dupa --to")

    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    stats = build(
        Path(os.getenv("BRONZE_DIR", "data/bronze")),
        Path(os.getenv("SILVER_DIR", "data/silver")),
        days,
    )
    print(f"randuri bronze citite: {stats.bronze_rows}")
    print(f"valide:                {stats.valid}")
    print(f"duplicate eliminate:   {stats.duplicates}")
    print(f"respinse:              {dict(stats.rejected) or 0}")
    for day, rows in stats.rows_per_day.items():
        print(f"silver {day}: {rows} randuri")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(main())
