from typing import Optional
from uuid import UUID

from fastapi import APIRouter

from app import db
from app.pipeline.filters import scrub_pii
from app.reporting import gap_why, load_run_view, run_info
from app.schemas import GapBucket, GapExample, GapsOut

router = APIRouter(tags=["gaps"])

MAX_EXAMPLES = 25

BUCKETS = (
    (
        "unmatched",
        "No vendor match",
        "The return couldn't be linked to an order line, SKU and vendor, so it isn't in any vendor's numbers.",
    ),
    (
        "junk",
        "Junk text",
        "The comment was blank or said nothing useful (\"ok\", an emoji). It was never sent to a model.",
    ),
    (
        "unclassified",
        "Couldn't classify",
        "Both models failed or were unsure, so the system left it for a person instead of guessing.",
    ),
)


@router.get("/gaps", response_model=GapsOut)
def gaps(run_id: Optional[UUID] = None) -> GapsOut:
    with db.connect() as conn:
        view = load_run_view(conn, run_id)

    buckets = []
    for key, label, explainer in BUCKETS:
        rows = view.with_status(key)
        buckets.append(
            GapBucket(
                key=key,
                label=label,
                explainer=explainer,
                count=len(rows),
                examples=[
                    GapExample(
                        return_id=r["return_id"],
                        text=scrub_pii(r["other_text"]),
                        why=gap_why(r),
                        order_line_id=r["order_line_id"],
                    )
                    for r in rows[:MAX_EXAMPLES]
                ],
            )
        )
    return GapsOut(run=run_info(view.run), total=len(view.rows), buckets=buckets)
