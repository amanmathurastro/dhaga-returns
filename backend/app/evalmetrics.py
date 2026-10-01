"""Arithmetic for scripts/eval.py. Pure functions: no model calls, no database.

An eval row holds the human label plus Model A's and Model B's attempt at the
same comment. Routing at any threshold can then be replayed offline, which is
how CONFIDENCE_THRESHOLD is chosen.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Guess:
    reason: Optional[str]  # None = the call failed or the output was invalid
    confidence: Optional[float] = None

    def accepted(self, threshold: float) -> bool:
        return self.reason is not None and (self.confidence or 0) >= threshold


@dataclass(frozen=True)
class EvalRow:
    return_id: str
    label: str
    a: Guess
    b: Guess


def routed_guess(row: EvalRow, threshold: float) -> tuple[Optional[str], str]:
    """(predicted reason or None if unclassified, model used) under the routing rule."""
    if row.a.accepted(threshold):
        return row.a.reason, "A"
    if row.b.accepted(threshold):
        return row.b.reason, "B"
    return None, "none"


def _share(n: int, total: int) -> Optional[float]:
    return n / total if total else None


def accuracy(pairs: list[tuple[str, Optional[str]]]) -> Optional[float]:
    """Share of (label, prediction) pairs that agree. A failed or unclassified row counts as wrong."""
    return _share(sum(1 for label, pred in pairs if label == pred), len(pairs))


def per_reason_accuracy(pairs: list[tuple[str, Optional[str]]]) -> dict[str, tuple[int, int]]:
    """label -> (correct, total)."""
    out: dict[str, list[int]] = {}
    for label, pred in pairs:
        correct_total = out.setdefault(label, [0, 0])
        correct_total[0] += int(label == pred)
        correct_total[1] += 1
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def confusion(pairs: list[tuple[str, Optional[str]]]) -> Counter:
    """(label, prediction) -> count. Prediction is '(none)' for failed / unclassified."""
    return Counter((label, pred or "(none)") for label, pred in pairs)


@dataclass
class ThresholdResult:
    threshold: float
    accuracy_on_answered: Optional[float]  # of the rows the system answered, how many were right
    accuracy_overall: Optional[float]  # unclassified counted as wrong
    routed_share: Optional[float]  # share sent to Model B
    unclassified_share: Optional[float]


def at_threshold(rows: list[EvalRow], threshold: float) -> ThresholdResult:
    guesses = [(row.label, *routed_guess(row, threshold)) for row in rows]
    answered = [(label, pred) for label, pred, _ in guesses if pred is not None]
    return ThresholdResult(
        threshold=threshold,
        accuracy_on_answered=accuracy(answered),
        accuracy_overall=accuracy([(label, pred) for label, pred, _ in guesses]),
        routed_share=_share(sum(1 for row in rows if not row.a.accepted(threshold)), len(rows)),
        unclassified_share=_share(sum(1 for _, pred, _ in guesses if pred is None), len(rows)),
    )


@dataclass
class ConfidenceSeparation:
    mean_when_right: Optional[float]
    mean_when_wrong: Optional[float]
    n_right: int
    n_wrong: int


def confidence_separation(rows: list[EvalRow], model: str = "a") -> ConfidenceSeparation:
    """Does self-reported confidence actually differ between right and wrong answers?"""
    right, wrong = [], []
    for row in rows:
        guess: Guess = getattr(row, model)
        if guess.reason is None or guess.confidence is None:
            continue
        (right if guess.reason == row.label else wrong).append(guess.confidence)
    mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return ConfidenceSeparation(mean(right), mean(wrong), len(right), len(wrong))
