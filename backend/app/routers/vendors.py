from collections import Counter
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter

from app import db
from app.errors import ApiError
from app.pipeline.aggregate import top_skus
from app.reporting import comment, load_run_view, run_info, vendor_row
from app.schemas import (
    BriefOut,
    LabelCount,
    NonVendorGroup,
    NonVendorOut,
    SkuOut,
    VendorBrief,
    VendorDetailOut,
    VendorsOut,
)
from app.taxonomy import (
    FIT_AREA_LABELS,
    FIT_DIRECTION_LABELS,
    NOT_VENDOR,
    REASON_INFO,
    VENDOR_TABLE_REASONS,
    category_label,
    reason_label,
)

router = APIRouter(tags=["vendors"])

MAX_COMMENTS = 100
MAX_EXAMPLES = 8


@router.get("/vendors", response_model=VendorsOut)
def vendors(
    run_id: Optional[UUID] = None,
    category: Optional[Literal["womenswear", "kidswear", "mens"]] = None,
) -> VendorsOut:
    with db.connect() as conn:
        view = load_run_view(conn, run_id)

    rows = [vendor_row(s, view.vendors) for s in view.segments if category is None or s.category == category]
    # Flagged first, then by the worst vendor-caused multiple of the category average.
    rows.sort(
        key=lambda r: (
            not r.flagged,
            -max((c.lift or 0) for c in r.cells if c.can_flag),
            r.vendor_name,
        )
    )
    return VendorsOut(
        run=run_info(view.run),
        thresholds=view.thresholds,
        category=category,
        rows=rows,
        unclassified=view.count("unclassified"),
        unmatched=view.count("unmatched"),
    )


def _brief(conn, run_id: UUID, vendor_id: str) -> BriefOut:
    stored = db.fetch_brief(conn, run_id, vendor_id)
    if stored is None:
        return BriefOut(status="not_written")
    if stored["status"] == "ok":
        return BriefOut(status="ok", brief=VendorBrief.model_validate(stored["brief"]))
    # A rejected brief's text is never returned, only why it was rejected.
    return BriefOut(status=stored["status"], problems=(stored["brief"] or {}).get("problems", []))


def _label_counts(counter: Counter, labels: dict[str, str]) -> list[LabelCount]:
    return [LabelCount(key=k, label=labels.get(k, k), count=n) for k, n in counter.most_common()]


@router.get("/vendors/{vendor_id}", response_model=VendorDetailOut)
def vendor_detail(vendor_id: str, run_id: Optional[UUID] = None) -> VendorDetailOut:
    with db.connect() as conn:
        view = load_run_view(conn, run_id)
        vendor = view.vendors.get(vendor_id)
        if vendor is None:
            raise ApiError(404, "vendor_not_found", "That vendor doesn't exist.")
        brief = _brief(conn, view.run["run_id"], vendor_id)

    segments = [s for s in view.segments if s.vendor_id == vendor_id]
    directions: Counter = Counter()
    areas: Counter = Counter()
    for seg in segments:
        directions.update(seg.fit_directions)
        areas.update(seg.fit_areas)

    rows = [r for r in view.rows if r["status"] == "classified" and r["vendor_id"] == vendor_id]
    sku_info = {r["sku_id"]: r for r in rows}
    # Vendor-related comments first, most common reason on top: they are the evidence for this page.
    frequency = Counter(r["reason"] for r in rows)
    rows.sort(
        key=lambda r: (r["reason"] not in VENDOR_TABLE_REASONS, -frequency[r["reason"]], r["reason"], r["return_id"])
    )

    return VendorDetailOut(
        run=run_info(view.run),
        thresholds=view.thresholds,
        vendor_id=vendor_id,
        vendor_name=vendor["name"],
        city=vendor.get("city"),
        segments=[vendor_row(s, view.vendors) for s in segments],
        fit_directions=_label_counts(directions, FIT_DIRECTION_LABELS),
        fit_areas=_label_counts(areas, FIT_AREA_LABELS),
        top_skus=[
            SkuOut(
                sku_id=s.sku_id,
                product_name=sku_info[s.sku_id]["product_name"],
                category_label=category_label(sku_info[s.sku_id]["category"]),
                is_live=sku_info[s.sku_id]["is_live"],
                units_sold=s.units_sold,
                returns=s.returns,
                rate=s.rate,
                top_reason_label=reason_label(s.top_reason),
            )
            for s in top_skus(view.sales, view.returns, vendor_id)
        ],
        comments=[comment(r) for r in rows[:MAX_COMMENTS]],
        comments_total=len(rows),
        brief=brief,
    )


@router.get("/non-vendor", response_model=NonVendorOut)
def non_vendor(run_id: Optional[UUID] = None) -> NonVendorOut:
    with db.connect() as conn:
        view = load_run_view(conn, run_id)

    classified = view.with_status("classified")
    groups = []
    for reason in NOT_VENDOR:
        rows = [r for r in classified if r["reason"] == reason]
        groups.append(
            NonVendorGroup(
                reason=reason,
                label=REASON_INFO[reason].label,
                likely_owner=REASON_INFO[reason].likely_owner,
                count=len(rows),
                share=len(rows) / len(classified) if classified else None,
                examples=[comment(r) for r in rows[:MAX_EXAMPLES]],
            )
        )
    return NonVendorOut(run=run_info(view.run), classified_total=len(classified), groups=groups)
