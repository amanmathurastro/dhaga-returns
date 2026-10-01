from functools import lru_cache

from fastapi import APIRouter

from app.config import get_settings
from app.pipeline import classify as classify_mod
from app.pipeline.filters import JUNK_REASON_LABELS, junk_reason, scrub_pii
from app.schemas import PreviewOut, PreviewRequest
from app.taxonomy import FIT_DIRECTION_LABELS, REASON_INFO

router = APIRouter(prefix="/classify", tags=["classify"])


@lru_cache
def _classifiers():
    settings = get_settings()
    return (
        classify_mod.safe_build(classify_mod.build_classifier, settings.MODEL_A_ID),
        classify_mod.safe_build(classify_mod.build_classifier, settings.MODEL_B_ID),
    )


@router.post("/preview", response_model=PreviewOut)
def preview(body: PreviewRequest) -> PreviewOut:
    """Classify one comment live, through the same scrub -> junk filter -> routing as a run."""
    settings = get_settings()
    threshold = settings.CONFIDENCE_THRESHOLD
    scrubbed = scrub_pii(body.text)

    why_junk = junk_reason(scrubbed, settings.JUNK_MIN_CHARS)
    if why_junk:
        return PreviewOut(
            status="junk",
            scrubbed_text=scrubbed,
            model_used="none",
            routed=False,
            confidence_threshold=threshold,
            detail=JUNK_REASON_LABELS[why_junk] + ". Not sent to a model.",
        )

    model_a, model_b = _classifiers()
    result = classify_mod.route(scrubbed, model_a, model_b, threshold)
    c = result.classification
    return PreviewOut(
        status=result.status,
        scrubbed_text=scrubbed,
        classification=c,
        reason_label=REASON_INFO[c.reason].label if c else None,
        fit_direction_label=FIT_DIRECTION_LABELS.get(c.fit_direction or "") if c else None,
        likely_owner=REASON_INFO[c.reason].likely_owner if c else None,
        model_used=result.model_used,
        routed=result.routed,
        confidence_threshold=threshold,
        detail=result.error,
    )
