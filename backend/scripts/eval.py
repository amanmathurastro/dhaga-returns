"""Evaluate classification against the hand-labelled subset.

    cd backend && python scripts/eval.py            # run both models on every labelled row
    python scripts/eval.py --threshold 0.7          # report routing at this threshold

Uses rows in `returns` where `human_label` is filled. Labels must be written by
team members independently, BEFORE they see any model output.

Reports (for the build note): accuracy per reason for Model A alone and for
A+B routing, the confusion matrix, how often routing fired, whether confidence
separates right from wrong answers, and cost.

Both models are called on every labelled row (so routing can be replayed at
any threshold). That costs more than a real run would; the labelled set is small.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.config import EVAL_REQUIRED, ConfigError, get_settings  # noqa: E402
from app.evalmetrics import (  # noqa: E402
    EvalRow, Guess, accuracy, at_threshold, confidence_separation, confusion,
    per_reason_accuracy, routed_guess,
)
from app.pipeline import classify as classify_mod  # noqa: E402
from app.pipeline.filters import junk_reason, scrub_pii  # noqa: E402
from app.pipeline.load import is_other  # noqa: E402
from app.taxonomy import REASONS  # noqa: E402

SWEEP = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)


def pct(x) -> str:
    return "   n/a" if x is None else f"{x * 100:5.1f}%"


def guess_of(attempt) -> Guess:
    c = attempt.classification
    return Guess(c.reason, c.confidence) if c else Guess(None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--threshold", type=float, help="confidence threshold to report (default: CONFIDENCE_THRESHOLD from .env)")
    args = parser.parse_args()

    try:
        settings = get_settings(EVAL_REQUIRED)
    except ConfigError as exc:
        print(f"Can't run eval. {exc}")
        return 1
    threshold = args.threshold if args.threshold is not None else settings.CONFIDENCE_THRESHOLD

    with db.connect() as conn:
        returns = db.fetch_returns(conn)

    labelled, skipped = [], []
    for r in returns:
        label = (r.get("human_label") or "").strip()
        if not label or not is_other(r):
            continue
        text = scrub_pii(r.get("other_text"))
        if label not in REASONS:
            skipped.append(f"{r['return_id']}: label '{label}' is not a reason in taxonomy.py")
        elif junk_reason(text, settings.JUNK_MIN_CHARS):
            skipped.append(f"{r['return_id']}: comment is junk, a real run would never send it to a model")
        else:
            labelled.append((r["return_id"], label, text))

    for line in skipped:
        print("skipped", line)
    if not labelled:
        print("No labelled rows. Fill `human_label` in backend/data/returns.csv (independently, before "
              "looking at model output), re-run scripts/seed.py, then run this again.")
        return 1

    try:
        model_a = classify_mod.build_classifier(settings.MODEL_A_ID)
        model_b = classify_mod.build_classifier(settings.MODEL_B_ID)
    except NotImplementedError as exc:
        print(exc)
        return 1

    print(f"Evaluating {len(labelled)} labelled comments")
    print(f"  Model A: {settings.MODEL_A_ID}\n  Model B: {settings.MODEL_B_ID}\n")

    def run_both(item):
        return (
            classify_mod.attempt("A", model_a, item[2]),
            classify_mod.attempt("B", model_b, item[2]),
        )

    with ThreadPoolExecutor(max_workers=settings.CLASSIFY_CONCURRENCY) as pool:
        attempts = list(pool.map(run_both, labelled))

    rows = [
        EvalRow(return_id, label, guess_of(a), guess_of(b))
        for (return_id, label, _), (a, b) in zip(labelled, attempts)
    ]
    failures = [(rid, a.error) for (rid, _, _), (a, _) in zip(labelled, attempts) if not a.valid]
    failures += [(rid, b.error) for (rid, _, _), (_, b) in zip(labelled, attempts) if not b.valid]

    a_pairs = [(r.label, r.a.reason) for r in rows]
    b_pairs = [(r.label, r.b.reason) for r in rows]
    print("== Accuracy, each model alone (no threshold; failed calls count as wrong) ==")
    print(f"  Model A: {pct(accuracy(a_pairs))}      Model B: {pct(accuracy(b_pairs))}")

    print("\n== Model A alone, per reason (correct / total) ==")
    for reason, (ok, total) in per_reason_accuracy(a_pairs).items():
        print(f"  {reason:<22} {ok:>3} / {total:<3} {pct(ok / total)}")

    print("\n== Does confidence separate right from wrong? ==")
    for name in ("a", "b"):
        sep = confidence_separation(rows, name)
        fmt = lambda x: "n/a" if x is None else f"{x:.2f}"  # noqa: E731
        print(f"  Model {name.upper()}: mean confidence when right {fmt(sep.mean_when_right)} (n={sep.n_right}), "
              f"when wrong {fmt(sep.mean_when_wrong)} (n={sep.n_wrong})")
    print("  If these two numbers are close, the threshold is not doing real work. Say so in the build note.")

    print("\n== Routing replayed at different thresholds ==")
    print("  threshold | right, of answered | right, overall | sent to B | unclassified")
    for t in SWEEP:
        res = at_threshold(rows, t)
        print(f"     {t:4.2f}   |      {pct(res.accuracy_on_answered)}        |    {pct(res.accuracy_overall)}     |"
              f"  {pct(res.routed_share)}  |   {pct(res.unclassified_share)}")

    if threshold is None:
        print("\nCONFIDENCE_THRESHOLD is not set yet. Pick one from the table above, put it in .env,\n"
              "and defend the choice in the "Build note" section of README.md.")
    else:
        routed_pairs = [(r.label, routed_guess(r, threshold)[0]) for r in rows]
        print(f"\n== A+B routing at threshold {threshold:.2f}, per reason (correct / total) ==")
        for reason, (ok, total) in per_reason_accuracy(routed_pairs).items():
            print(f"  {reason:<22} {ok:>3} / {total:<3} {pct(ok / total)}")
        print(f"\n== Confusion at threshold {threshold:.2f} (human label -> system answer, mistakes only) ==")
        mistakes = [(k, n) for k, n in confusion(routed_pairs).most_common() if k[0] != k[1]]
        for (label, pred), n in mistakes:
            print(f"  {label:<22} -> {pred:<22} x{n}")
        if not mistakes:
            print("  none")

    print("\n== Tokens (this eval: both models on every row) ==")
    n = len(rows)
    for name, idx in (("A", 0), ("B", 1)):
        tin = sum(pair[idx].input_tokens for pair in attempts)
        tout = sum(pair[idx].output_tokens for pair in attempts)
        if tin or tout:
            print(f"  Model {name}: avg {tin / n:.0f} input + {tout / n:.0f} output tokens per call")
        else:
            print(f"  Model {name}: no token counts returned by the classifier (see LLMResult in classify.py)")
    print("  Multiply by OpenRouter prices for the cost line in the build note (plan §13).")

    if failures:
        print(f"\n== {len(failures)} failed call(s) ==")
        for rid, err in failures[:10]:
            print(f"  {rid}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
