"""Supabase (Postgres) access. All SQL lives here. Server-side only."""

from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import DB_REQUIRED, get_settings

Row = dict[str, Any]


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """One short-lived connection. Commits on success, rolls back on error."""
    url = get_settings(DB_REQUIRED).SUPABASE_DB_URL
    # prepare_threshold=None: Supabase's transaction pooler does not support prepared statements.
    with psycopg.connect(url, row_factory=dict_row, prepare_threshold=None, connect_timeout=10) as conn:
        yield conn


def ping() -> bool:
    try:
        with connect() as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Source data
# --------------------------------------------------------------------------


def fetch_returns(conn) -> list[Row]:
    return conn.execute(
        "select return_id, order_line_id, return_date, dropdown_reason, other_text, human_label from returns"
    ).fetchall()


def fetch_order_lines(conn) -> list[Row]:
    return conn.execute(
        """
        select ol.order_line_id, ol.sku_id, ol.size, ol.quantity, o.order_date
        from order_lines ol
        left join orders o on o.order_id = ol.order_id
        """
    ).fetchall()


def fetch_skus(conn) -> list[Row]:
    return conn.execute("select sku_id, vendor_id, category, product_name, is_live from skus").fetchall()


def fetch_vendors(conn) -> list[Row]:
    return conn.execute("select vendor_id, name, city from vendors").fetchall()


def fetch_sales(conn, period_start: Optional[date], period_end: Optional[date]) -> list[Row]:
    """Units sold per vendor / category / SKU for orders placed in the period."""
    return conn.execute(
        """
        select s.vendor_id, s.category, s.sku_id, sum(ol.quantity)::int as units
        from order_lines ol
        join orders o on o.order_id = ol.order_id
        join skus s on s.sku_id = ol.sku_id
        join vendors v on v.vendor_id = s.vendor_id
        where (%(start)s::date is null or o.order_date >= %(start)s::date)
          and (%(end)s::date is null or o.order_date <= %(end)s::date)
        group by s.vendor_id, s.category, s.sku_id
        """,
        {"start": period_start, "end": period_end},
    ).fetchall()


# --------------------------------------------------------------------------
# Pipeline runs
# --------------------------------------------------------------------------


def create_run(
    conn,
    *,
    model_a_id: str,
    model_b_id: str,
    period_start: Optional[date],
    period_end: Optional[date],
    params: dict,
) -> Optional[UUID]:
    """Insert a 'running' run. Returns None if another run is already running."""
    row = conn.execute(
        """
        insert into pipeline_runs (status, model_a_id, model_b_id, period_start, period_end, params)
        select 'running', %s, %s, %s, %s, %s
        where not exists (select 1 from pipeline_runs where status = 'running')
        returning run_id
        """,
        (model_a_id, model_b_id, period_start, period_end, Jsonb(params)),
    ).fetchone()
    return row["run_id"] if row else None


def finish_run(
    conn,
    run_id: UUID,
    *,
    status: str,
    counts: Optional[dict] = None,
    cost_usd: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    conn.execute(
        """
        update pipeline_runs
        set status = %s, finished_at = now(), counts = %s, cost_usd = %s, error = %s
        where run_id = %s
        """,
        (status, Jsonb(counts) if counts is not None else None, cost_usd, error, run_id),
    )


def fail_stale_runs(conn) -> int:
    """Runs still 'running' when the server starts were cut off by a restart."""
    return conn.execute(
        """
        update pipeline_runs
        set status = 'failed', finished_at = now(),
            error = 'The server restarted while this run was in progress.'
        where status = 'running'
        """
    ).rowcount


def get_run(conn, run_id: UUID) -> Optional[Row]:
    return conn.execute("select * from pipeline_runs where run_id = %s", (run_id,)).fetchone()


def latest_done_run(conn) -> Optional[Row]:
    return conn.execute(
        "select * from pipeline_runs where status = 'done' order by started_at desc limit 1"
    ).fetchone()


def list_runs(conn, limit: int = 10) -> list[Row]:
    return conn.execute(
        "select * from pipeline_runs order by started_at desc limit %s", (limit,)
    ).fetchall()


# --------------------------------------------------------------------------
# Pipeline results
# --------------------------------------------------------------------------

_CLASSIFICATION_COLUMNS = (
    "return_id", "status", "reason", "fit_direction", "fit_area", "secondary_reason",
    "confidence", "gist_en", "model_used", "error",
)


def save_classifications(conn, run_id: UUID, rows: list[Row]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            insert into return_classifications (run_id, {", ".join(_CLASSIFICATION_COLUMNS)})
            values (%s, {", ".join(["%s"] * len(_CLASSIFICATION_COLUMNS))})
            """,
            [(run_id, *(row.get(col) for col in _CLASSIFICATION_COLUMNS)) for row in rows],
        )


def save_briefs(conn, run_id: UUID, briefs: list[Row]) -> None:
    if not briefs:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "insert into vendor_briefs (run_id, vendor_id, brief, status) values (%s, %s, %s, %s)",
            [(run_id, b["vendor_id"], Jsonb(b["brief"]), b["status"]) for b in briefs],
        )


def fetch_run_rows(conn, run_id: UUID) -> list[Row]:
    """Every classification row of a run, with its comment and (where matched) SKU and vendor."""
    return conn.execute(
        """
        select rc.return_id, rc.status, rc.reason, rc.fit_direction, rc.fit_area,
               rc.secondary_reason, rc.confidence::float as confidence, rc.gist_en,
               rc.model_used, rc.error,
               r.other_text, r.order_line_id, r.return_date,
               ol.size, s.sku_id, s.product_name, s.category, s.is_live,
               v.vendor_id, v.name as vendor_name
        from return_classifications rc
        join returns r on r.return_id = rc.return_id
        left join order_lines ol on ol.order_line_id = r.order_line_id
        left join skus s on s.sku_id = ol.sku_id
        left join vendors v on v.vendor_id = s.vendor_id
        where rc.run_id = %s
        order by rc.return_id
        """,
        (run_id,),
    ).fetchall()


def fetch_brief(conn, run_id: UUID, vendor_id: str) -> Optional[Row]:
    return conn.execute(
        "select brief, status from vendor_briefs where run_id = %s and vendor_id = %s",
        (run_id, vendor_id),
    ).fetchone()
