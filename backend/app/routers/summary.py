from collections import Counter
from typing import Optional
from uuid import UUID

from fastapi import APIRouter

from app import db
from app.reporting import load_run_view, run_info
from app.schemas import CoverageItem, ReasonCount, SummaryOut
from app.taxonomy import REASON_INFO

router = APIRouter(tags=["summary"])

COVERAGE_LABELS = {
    "classified": "Classified",
    "junk": "Junk text",
    "unmatched": "No vendor match",
    "unclassified": "Couldn't classify",
}


@router.get("/summary", response_model=SummaryOut)
def summary(run_id: Optional[UUID] = None) -> SummaryOut:
    with db.connect() as conn:
        view = load_run_view(conn, run_id)

    total = len(view.rows)
    classified = view.with_status("classified")
    by_reason = Counter(r["reason"] for r in classified)
    counts = view.run["counts"] or {}

    return SummaryOut(
        run=run_info(view.run),
        other_returns=total,
        dropdown_returns_not_analysed=counts.get("dropdown_not_analysed", 0),
        units_sold=sum(s.units for s in view.sales),
        coverage=[
            CoverageItem(key=key, label=label, count=view.count(key), share=view.count(key) / total if total else None)
            for key, label in COVERAGE_LABELS.items()
        ],
        reasons=[
            ReasonCount(
                reason=info.key,
                label=info.label,
                group=info.group,
                likely_owner=info.likely_owner,
                count=by_reason[info.key],
                share=by_reason[info.key] / len(classified) if classified else None,
            )
            for info in REASON_INFO.values()
        ],
        routed_to_model_b=counts.get("routed", 0),
        flagged_vendors=len({s.vendor_id for s in view.segments if s.flagged}),
    )
