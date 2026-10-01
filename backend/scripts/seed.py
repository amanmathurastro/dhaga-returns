"""Load the CSVs in backend/data/ into Supabase.

    cd backend && python scripts/seed.py           # insert / update rows (safe to re-run)
    python scripts/seed.py --reset                 # delete ALL data and pipeline results first

Run supabase/schema.sql first. Blank CSV cells are stored as NULL.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.config import ConfigError  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# Parent tables first (foreign keys). (table, primary key, columns)
TABLES = (
    ("vendors", "vendor_id", ("vendor_id", "name", "city")),
    ("skus", "sku_id", ("sku_id", "vendor_id", "category", "product_name", "is_live")),
    ("orders", "order_id", ("order_id", "order_date", "payment_mode")),
    ("order_lines", "order_line_id", ("order_line_id", "order_id", "sku_id", "size", "quantity")),
    ("returns", "return_id", ("return_id", "order_line_id", "return_date", "dropdown_reason", "other_text", "human_label")),
)


def read_csv(table: str, columns: tuple[str, ...]) -> list[tuple]:
    path = DATA_DIR / f"{table}.csv"
    if not path.exists():
        raise SystemExit(f"Missing {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{path.name} is missing column(s): {', '.join(missing)}")
        return [tuple((row[c] or "").strip() or None for c in columns) for row in reader]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--reset", action="store_true",
                        help="delete ALL existing data and pipeline results first")
    args = parser.parse_args()

    data = {table: read_csv(table, columns) for table, _, columns in TABLES}

    try:
        with db.connect() as conn:
            if args.reset:
                conn.execute(
                    "truncate vendor_briefs, return_classifications, pipeline_runs, "
                    "returns, order_lines, orders, skus, vendors"
                )
                print("Deleted existing data and pipeline results.")
            for table, key, columns in TABLES:
                updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != key)
                with conn.cursor() as cur:
                    cur.executemany(
                        f"insert into {table} ({', '.join(columns)}) "
                        f"values ({', '.join(['%s'] * len(columns))}) "
                        f"on conflict ({key}) do update set {updates}",
                        data[table],
                    )
                print(f"{table:<12} {len(data[table]):>5} rows")
    except ConfigError as exc:
        print(f"Can't seed. {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
