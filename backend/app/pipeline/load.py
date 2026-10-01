"""Pick the "Other" returns and join each one to its order line, SKU and vendor.

Pure functions over rows (dicts) so the join can be tested without a database.
A return that cannot be joined is kept and marked unmatched. It is never dropped.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional

Row = Mapping[str, Any]


def is_other(return_row: Row) -> bool:
    return (return_row.get("dropdown_reason") or "").strip().lower() == "other"


@dataclass(frozen=True)
class JoinedReturn:
    return_id: str
    text: Optional[str]
    return_date: Optional[date]
    order_line_id: Optional[str] = None
    sku_id: Optional[str] = None
    vendor_id: Optional[str] = None
    category: Optional[str] = None
    size: Optional[str] = None
    order_date: Optional[date] = None
    unmatched_why: Optional[str] = None

    @property
    def matched(self) -> bool:
        return self.unmatched_why is None


def join_returns(
    returns: Iterable[Row],
    order_lines: Iterable[Row],
    skus: Iterable[Row],
    vendors: Iterable[Row],
) -> list[JoinedReturn]:
    """Join return -> order line -> SKU -> vendor.

    `order_lines` rows carry `order_date` (from their order). Pulled SKUs
    (`is_live = false`) still resolve to their vendor.
    """
    lines = {ol["order_line_id"]: ol for ol in order_lines}
    sku_by_id = {s["sku_id"]: s for s in skus}
    vendor_ids = {v["vendor_id"] for v in vendors}

    joined: list[JoinedReturn] = []
    for r in returns:
        base = dict(return_id=r["return_id"], text=r.get("other_text"), return_date=r.get("return_date"))
        line_id = (r.get("order_line_id") or "").strip() or None
        if line_id is None:
            joined.append(JoinedReturn(**base, unmatched_why="Return has no order line ID"))
            continue
        line = lines.get(line_id)
        if line is None:
            joined.append(
                JoinedReturn(**base, order_line_id=line_id, unmatched_why="Order line ID not found in orders")
            )
            continue
        base.update(order_line_id=line_id, size=line.get("size"), order_date=line.get("order_date"))
        sku = sku_by_id.get(line.get("sku_id"))
        if sku is None:
            joined.append(JoinedReturn(**base, sku_id=line.get("sku_id"), unmatched_why="SKU not found in catalogue"))
            continue
        base.update(sku_id=sku["sku_id"], category=sku.get("category"))
        vendor_id = sku.get("vendor_id")
        if vendor_id is None or vendor_id not in vendor_ids:
            joined.append(JoinedReturn(**base, unmatched_why="SKU has no vendor on record"))
            continue
        joined.append(JoinedReturn(**base, vendor_id=vendor_id))
    return joined


def in_period(j: JoinedReturn, start: Optional[date], end: Optional[date]) -> bool:
    """The period is about when the order was placed, so returns line up with units sold.

    An unmatched return has no order date, so its return date is used instead.
    """
    d = j.order_date if j.matched else j.return_date
    if d is None:
        return start is None and end is None
    if start is not None and d < start:
        return False
    if end is not None and d > end:
        return False
    return True
