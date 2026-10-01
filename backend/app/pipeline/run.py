"""Orchestrates one pipeline run.

    load "Other" returns -> join to vendor -> junk filter + PII scrub
      -> classify (Model A, then B)            [model]
      -> rates, category averages, flags       [code]
      -> vendor brief for flagged vendors      [model]
      -> check brief numbers against the table [code]

`process` is pure (no database, models passed in) so the whole chain can be
tested with fake models. `execute_run` wraps it with the database.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID

from app import db
from app.config import Settings, get_settings
from app.pipeline import brief as brief_mod
from app.pipeline import classify as classify_mod
from app.pipeline.aggregate import ClassifiedReturn, Sale, Segment, aggregate
from app.pipeline.brief import BRIEF_MAX_COMMENTS, BriefComment, BriefInput, BriefOutcome, BriefWriter
from app.pipeline.classify import Classifier, RoutedResult, route
from app.pipeline.filters import junk_reason, scrub_pii
from app.pipeline.load import JoinedReturn, in_period, is_other, join_returns
from app.taxonomy import VENDOR_TABLE_REASONS

log = logging.getLogger("dhaga.pipeline")


@dataclass
class RunInputs:
    returns: list[dict]
    order_lines: list[dict]
    skus: list[dict]
    vendors: list[dict]
    sales: list[Sale]  # already limited to the period


@dataclass
class RunDeps:
    classifier_a: Classifier
    classifier_b: Classifier
    brief_writer: BriefWriter
    confidence_threshold: float
    min_returns_to_flag: int
    lift_threshold: float
    junk_min_chars: int = 3
    concurrency: int = 8


@dataclass
class RunOutput:
    classifications: list[dict] = field(default_factory=list)
    briefs: list[dict] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)


def _row(return_id: str, status: str, error: Optional[str] = None, result: Optional[RoutedResult] = None) -> dict:
    row = {
        "return_id": return_id, "status": status, "reason": None, "fit_direction": None,
        "fit_area": None, "secondary_reason": None, "confidence": None, "gist_en": None,
        "model_used": "none", "error": error,
    }
    if result is not None:
        row["model_used"] = result.model_used
        row["error"] = result.error
        if result.classification is not None:
            row.update(result.classification.model_dump())
    return row


def brief_inputs(
    segments: list[Segment],
    classified: list[tuple[JoinedReturn, str, RoutedResult]],
    vendor_names: dict[str, str],
) -> list[BriefInput]:
    """One BriefInput per vendor that has at least one flag."""
    by_vendor: dict[str, list[Segment]] = {}
    for seg in segments:
        by_vendor.setdefault(seg.vendor_id, []).append(seg)

    inputs = []
    for vendor_id, vendor_segments in sorted(by_vendor.items()):
        if not any(s.flagged for s in vendor_segments):
            continue
        comments = [
            BriefComment(
                return_id=j.return_id,
                text=text,
                gist_en=r.classification.gist_en,
                reason=r.classification.reason,
                fit_direction=r.classification.fit_direction,
            )
            for j, text, r in classified
            if j.vendor_id == vendor_id and r.classification.reason in VENDOR_TABLE_REASONS
        ]
        inputs.append(
            BriefInput(
                vendor_id=vendor_id,
                vendor_name=vendor_names.get(vendor_id, vendor_id),
                metrics=brief_mod.vendor_metrics(vendor_segments),
                flagged_metric_keys=brief_mod.flagged_keys(vendor_segments),
                comments=comments[:BRIEF_MAX_COMMENTS],
            )
        )
    return inputs


def process(
    inputs: RunInputs,
    deps: RunDeps,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> RunOutput:
    out = RunOutput()

    other = [r for r in inputs.returns if is_other(r)]
    joined = join_returns(other, inputs.order_lines, inputs.skus, inputs.vendors)
    in_scope = [j for j in joined if in_period(j, period_start, period_end)]

    to_classify: list[tuple[JoinedReturn, str]] = []
    counts = {"junk": 0, "unmatched": 0, "classified": 0, "unclassified": 0, "routed": 0}
    for j in in_scope:
        if not j.matched:
            out.classifications.append(_row(j.return_id, "unmatched", j.unmatched_why))
            counts["unmatched"] += 1
            continue
        scrubbed = scrub_pii(j.text)
        why_junk = junk_reason(scrubbed, deps.junk_min_chars)
        if why_junk:
            out.classifications.append(_row(j.return_id, "junk", why_junk))
            counts["junk"] += 1
            continue
        to_classify.append((j, scrubbed))

    # Concurrency here is for throughput only. It is not the "parallelization" pattern.
    with ThreadPoolExecutor(max_workers=deps.concurrency) as pool:
        results = list(
            pool.map(
                lambda item: route(item[1], deps.classifier_a, deps.classifier_b, deps.confidence_threshold),
                to_classify,
            )
        )

        tokens = {"a_in": 0, "a_out": 0, "b_in": 0, "b_out": 0, "brief_in": 0, "brief_out": 0}
        classified: list[tuple[JoinedReturn, str, RoutedResult]] = []
        for (j, text), result in zip(to_classify, results):
            out.classifications.append(_row(j.return_id, result.status, result=result))
            counts[result.status] += 1
            counts["routed"] += int(result.routed)
            for a in result.attempts:
                tokens[f"{a.model.lower()}_in"] += a.input_tokens
                tokens[f"{a.model.lower()}_out"] += a.output_tokens
            if result.status == "classified":
                classified.append((j, text, result))

        out.segments = aggregate(
            inputs.sales,
            [
                ClassifiedReturn(
                    j.return_id, j.vendor_id, j.category, j.sku_id,
                    r.classification.reason, r.classification.fit_direction, r.classification.fit_area,
                )
                for j, _, r in classified
            ],
            min_returns_to_flag=deps.min_returns_to_flag,
            lift_threshold=deps.lift_threshold,
        )

        vendor_names = {v["vendor_id"]: v.get("name") or v["vendor_id"] for v in inputs.vendors}
        to_brief = brief_inputs(out.segments, classified, vendor_names)
        outcomes: list[BriefOutcome] = list(
            pool.map(lambda bi: brief_mod.write_brief(bi, deps.brief_writer), to_brief)
        )

    brief_counts = {"ok": 0, "rejected_numbers_mismatch": 0, "failed": 0}
    for outcome in outcomes:
        out.briefs.append({"vendor_id": outcome.vendor_id, "status": outcome.status, "brief": outcome.to_json()})
        brief_counts[outcome.status] += 1
        tokens["brief_in"] += outcome.input_tokens
        tokens["brief_out"] += outcome.output_tokens

    out.counts = {
        "processed": len(in_scope),
        **counts,
        "dropdown_not_analysed": len(inputs.returns) - len(other),
        "outside_period": len(joined) - len(in_scope),
        "briefs": brief_counts,
        "tokens": tokens,
    }
    return out


def cost_usd(tokens: dict[str, int], settings: Settings) -> Optional[float]:
    """Run cost from token counts and the prices in .env. None when it cannot be worked out."""
    prices = (
        settings.MODEL_A_INPUT_USD_PER_MTOK, settings.MODEL_A_OUTPUT_USD_PER_MTOK,
        settings.MODEL_B_INPUT_USD_PER_MTOK, settings.MODEL_B_OUTPUT_USD_PER_MTOK,
    )
    if any(p is None for p in prices) or not any(tokens.values()):
        return None
    a_in, a_out, b_in, b_out = prices
    total = (
        tokens["a_in"] * a_in + tokens["a_out"] * a_out
        + (tokens["b_in"] + tokens["brief_in"]) * b_in
        + (tokens["b_out"] + tokens["brief_out"]) * b_out
    )
    return round(total / 1_000_000, 6)


def run_params(settings: Settings) -> dict:
    """Thresholds a run was made with. Stored on the run so it keeps displaying consistently."""
    return {
        "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
        "min_returns_to_flag": settings.MIN_RETURNS_TO_FLAG,
        "lift_threshold": settings.LIFT_THRESHOLD,
        "junk_min_chars": settings.JUNK_MIN_CHARS,
    }


def execute_run(run_id: UUID, period_start: Optional[date] = None, period_end: Optional[date] = None) -> None:
    """Run the pipeline for an existing 'running' row and record the outcome. Never raises."""
    settings = get_settings()
    try:
        with db.connect() as conn:
            inputs = RunInputs(
                returns=db.fetch_returns(conn),
                order_lines=db.fetch_order_lines(conn),
                skus=db.fetch_skus(conn),
                vendors=db.fetch_vendors(conn),
                sales=[Sale(**row) for row in db.fetch_sales(conn, period_start, period_end)],
            )
        deps = RunDeps(
            classifier_a=classify_mod.safe_build(classify_mod.build_classifier, settings.MODEL_A_ID),
            classifier_b=classify_mod.safe_build(classify_mod.build_classifier, settings.MODEL_B_ID),
            brief_writer=classify_mod.safe_build(brief_mod.build_brief_writer, settings.MODEL_B_ID),
            confidence_threshold=settings.CONFIDENCE_THRESHOLD,
            min_returns_to_flag=settings.MIN_RETURNS_TO_FLAG,
            lift_threshold=settings.LIFT_THRESHOLD,
            junk_min_chars=settings.JUNK_MIN_CHARS,
            concurrency=settings.CLASSIFY_CONCURRENCY,
        )
        out = process(inputs, deps, period_start, period_end)
        with db.connect() as conn:  # one transaction: results and 'done' land together
            db.save_classifications(conn, run_id, out.classifications)
            db.save_briefs(conn, run_id, out.briefs)
            db.finish_run(
                conn, run_id, status="done", counts=out.counts,
                cost_usd=cost_usd(out.counts["tokens"], settings),
            )
    except Exception as exc:
        log.exception("Pipeline run %s failed", run_id)
        try:
            with db.connect() as conn:
                db.finish_run(conn, run_id, status="failed", error=classify_mod._short(exc, 400))
        except Exception:
            log.exception("Could not record failure of run %s", run_id)
