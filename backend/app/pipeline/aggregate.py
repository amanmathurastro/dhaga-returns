"""Rates per vendor x reason, category averages, lift and flags. Arithmetic only.

For each vendor v, product category c, reason r:

    units_sold(v, c)   = sum of order-line quantities for v's SKUs in c, in the period
    returns(v, c, r)   = classified returns for v in c with reason r
    rate(v, c, r)      = returns(v, c, r) / units_sold(v, c)
    category_avg(c, r) = returns in c with reason r / units sold in c
    lift(v, c, r)      = rate(v, c, r) / category_avg(c, r)
    flag(v, c, r)      = returns >= MIN_RETURNS_TO_FLAG and lift >= LIFT_THRESHOLD
                         (vendor-caused reasons only)

A vendor selling in two categories gets one segment per category, so each is
compared with the right category average.

ASK CLIENT: is the 31% return rate per order or per unit? This file counts
per unit sold. If their definition is per order, the denominator changes here.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.taxonomy import REASONS, UNKNOWN_CATEGORY, VENDOR_CAUSED


@dataclass(frozen=True)
class Sale:
    vendor_id: str
    category: Optional[str]
    sku_id: str
    units: int


@dataclass(frozen=True)
class ClassifiedReturn:
    return_id: str
    vendor_id: str
    category: Optional[str]
    sku_id: str
    reason: str
    fit_direction: Optional[str] = None
    fit_area: Optional[str] = None


@dataclass
class ReasonCell:
    reason: str
    returns: int
    rate: Optional[float]  # None when nothing was sold in the period
    category_avg: Optional[float]
    lift: Optional[float]  # None when the category average is 0
    flagged: bool


@dataclass
class Segment:
    vendor_id: str
    category: str
    units_sold: int
    returns_total: int
    cells: dict[str, ReasonCell]
    fit_directions: dict[str, int] = field(default_factory=dict)
    fit_areas: dict[str, int] = field(default_factory=dict)

    @property
    def flagged(self) -> bool:
        return any(c.flagged for c in self.cells.values())


def _ratio(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator > 0 else None


def aggregate(
    sales: Iterable[Sale],
    returns: Iterable[ClassifiedReturn],
    *,
    min_returns_to_flag: int,
    lift_threshold: float,
) -> list[Segment]:
    units: Counter[tuple[str, str]] = Counter()
    category_units: Counter[str] = Counter()
    for s in sales:
        category = s.category or UNKNOWN_CATEGORY
        units[(s.vendor_id, category)] += s.units
        category_units[category] += s.units

    counts: Counter[tuple[str, str, str]] = Counter()
    category_counts: Counter[tuple[str, str]] = Counter()
    directions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    areas: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for r in returns:
        category = r.category or UNKNOWN_CATEGORY
        key = (r.vendor_id, category)
        counts[(*key, r.reason)] += 1
        category_counts[(category, r.reason)] += 1
        if r.reason == "fit":
            directions[key][r.fit_direction or "unclear"] += 1
            if r.fit_area:
                areas[key][r.fit_area] += 1

    keys = set(units) | {(v, c) for v, c, _ in counts}
    segments: list[Segment] = []
    for vendor_id, category in sorted(keys):
        sold = units[(vendor_id, category)]
        cells: dict[str, ReasonCell] = {}
        for reason in REASONS:
            n = counts[(vendor_id, category, reason)]
            rate = _ratio(n, sold)
            avg = _ratio(category_counts[(category, reason)], category_units[category])
            lift = rate / avg if rate is not None and avg else None
            flagged = (
                reason in VENDOR_CAUSED
                and lift is not None
                and n >= min_returns_to_flag
                and lift >= lift_threshold
            )
            cells[reason] = ReasonCell(reason, n, rate, avg, lift, flagged)
        segments.append(
            Segment(
                vendor_id=vendor_id,
                category=category,
                units_sold=sold,
                returns_total=sum(c.returns for c in cells.values()),
                cells=cells,
                fit_directions=dict(directions[(vendor_id, category)]),
                fit_areas=dict(areas[(vendor_id, category)]),
            )
        )
    return segments


@dataclass
class SkuStat:
    sku_id: str
    units_sold: int
    returns: int
    rate: Optional[float]
    top_reason: Optional[str]


def top_skus(
    sales: Iterable[Sale], returns: Iterable[ClassifiedReturn], vendor_id: str, limit: int = 10
) -> list[SkuStat]:
    """A vendor's SKUs with the most classified returns."""
    sold: Counter[str] = Counter()
    for s in sales:
        if s.vendor_id == vendor_id:
            sold[s.sku_id] += s.units
    by_sku: dict[str, Counter[str]] = defaultdict(Counter)
    for r in returns:
        if r.vendor_id == vendor_id:
            by_sku[r.sku_id][r.reason] += 1
    stats = [
        SkuStat(
            sku_id=sku_id,
            units_sold=sold[sku_id],
            returns=sum(reasons.values()),
            rate=_ratio(sum(reasons.values()), sold[sku_id]),
            top_reason=reasons.most_common(1)[0][0],
        )
        for sku_id, reasons in by_sku.items()
    ]
    stats.sort(key=lambda s: (-s.returns, s.sku_id))
    return stats[:limit]
