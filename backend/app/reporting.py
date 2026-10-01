"""Read side: turn a stored run into what the dashboard shows.

Rates are recomputed from the stored classifications with the same `aggregate`
function the run used, and with the thresholds stored on the run, so the table
always agrees with the numbers the vendor briefs were checked against.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app import db
from app.config import get_settings
from app.errors import ApiError
from app.pipeline.aggregate import ClassifiedReturn, Sale, Segment, aggregate
from app.pipeline.filters import JUNK_REASON_LABELS, scrub_pii
from app.schemas import CellOut, CommentOut, RunInfo, Thresholds, VendorRow
from app.taxonomy import (
    FIT_DIRECTION_LABELS,
    REASON_INFO,
    UNKNOWN_CATEGORY,
    VENDOR_CAUSED,
    VENDOR_TABLE_REASONS,
    category_label,
    reason_label,
)


def run_info(row: dict) -> RunInfo:
    return RunInfo(
        run_id=str(row["run_id"]),
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        period_start=row.get("period_start"),
        period_end=row.get("period_end"),
        model_a_id=row["model_a_id"],
        model_b_id=row["model_b_id"],
        counts=row["counts"] or {},
        cost_usd=float(row["cost_usd"]) if row["cost_usd"] is not None else None,
        error=row.get("error"),
    )


def resolve_run(conn, run_id: Optional[UUID]) -> dict:
    """The run to display: the one asked for, else the latest successful one."""
    if run_id is None:
        run = db.latest_done_run(conn)
        if run is None:
            raise ApiError(404, "no_run", "No completed pipeline run yet. Press \"Run pipeline\" on the Summary page.")
        return run
    run = db.get_run(conn, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "That pipeline run doesn't exist.")
    if run["status"] != "done":
        raise ApiError(409, "run_not_done", f"That pipeline run is {run['status']}, so it has no results to show.")
    return run


@dataclass
class RunView:
    run: dict
    rows: list[dict]  # every classification row, with comment, SKU and vendor
    sales: list[Sale]
    returns: list[ClassifiedReturn]
    segments: list[Segment]
    thresholds: Thresholds
    vendors: dict[str, dict]

    def with_status(self, status: str) -> list[dict]:
        return [r for r in self.rows if r["status"] == status]

    def count(self, status: str) -> int:
        return sum(1 for r in self.rows if r["status"] == status)


def load_run_view(conn, run_id: Optional[UUID]) -> RunView:
    run = resolve_run(conn, run_id)
    params = run.get("params") or {}
    settings = get_settings()
    thresholds = Thresholds(
        min_returns_to_flag=params.get("min_returns_to_flag", settings.MIN_RETURNS_TO_FLAG),
        lift_threshold=params.get("lift_threshold", settings.LIFT_THRESHOLD),
    )
    rows = db.fetch_run_rows(conn, run["run_id"])
    sales = [Sale(**s) for s in db.fetch_sales(conn, run.get("period_start"), run.get("period_end"))]
    returns = [
        ClassifiedReturn(
            r["return_id"], r["vendor_id"], r["category"], r["sku_id"],
            r["reason"], r["fit_direction"], r["fit_area"],
        )
        for r in rows
        if r["status"] == "classified" and r["vendor_id"] is not None
    ]
    segments = aggregate(
        sales, returns,
        min_returns_to_flag=thresholds.min_returns_to_flag,
        lift_threshold=thresholds.lift_threshold,
    )
    vendors = {v["vendor_id"]: v for v in db.fetch_vendors(conn)}
    return RunView(run, rows, sales, returns, segments, thresholds, vendors)


def vendor_row(seg: Segment, vendors: dict[str, dict]) -> VendorRow:
    vendor = vendors.get(seg.vendor_id, {})
    return VendorRow(
        vendor_id=seg.vendor_id,
        vendor_name=vendor.get("name") or seg.vendor_id,
        city=vendor.get("city"),
        category=seg.category,
        category_label=category_label(seg.category) if seg.category != UNKNOWN_CATEGORY else "Uncategorised",
        units_sold=seg.units_sold,
        returns_total=seg.returns_total,
        cells=[
            CellOut(
                reason=reason,
                label=REASON_INFO[reason].label,
                can_flag=reason in VENDOR_CAUSED,
                returns=seg.cells[reason].returns,
                rate=seg.cells[reason].rate,
                category_avg=seg.cells[reason].category_avg,
                lift=seg.cells[reason].lift,
                flagged=seg.cells[reason].flagged,
            )
            for reason in VENDOR_TABLE_REASONS
        ],
        flagged=seg.flagged,
    )


def comment(row: dict) -> CommentOut:
    """A classified return as shown on the dashboard. The raw text is PII-scrubbed here."""
    return CommentOut(
        return_id=row["return_id"],
        text=scrub_pii(row["other_text"]),
        gist_en=row["gist_en"],
        reason=row["reason"],
        reason_label=reason_label(row["reason"]) if row["reason"] else None,
        fit_direction_label=FIT_DIRECTION_LABELS.get(row["fit_direction"] or ""),
        secondary_reason=row["secondary_reason"],
        size=row["size"],
        product_name=row["product_name"],
        model_used=row["model_used"],
        confidence=row["confidence"],
    )


def gap_why(row: dict) -> Optional[str]:
    if row["status"] == "junk":
        return JUNK_REASON_LABELS.get(row["error"] or "", row["error"])
    return row["error"]
