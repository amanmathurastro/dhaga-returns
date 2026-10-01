"""Return reasons and who owns each one.

DRAFT: Neha has not confirmed this list yet (ASK CLIENT, question 4).
The owner mapping lives here, in code. It is never asked of the model.
If a reason is added or renamed, also update `ReturnClassification` in schemas.py.
"""

from dataclasses import dataclass
from typing import Literal, Optional

Group = Literal["vendor", "unclear", "not_vendor", "other"]


@dataclass(frozen=True)
class ReasonInfo:
    key: str
    label: str
    group: Group
    vendor_caused: Optional[bool]  # None = unclear
    likely_owner: str


REASON_INFO: dict[str, ReasonInfo] = {
    r.key: r
    for r in (
        ReasonInfo("fit", "Fit / size", "vendor", True, "Vendor"),
        ReasonInfo("defect_quality", "Defect / quality", "vendor", True, "Vendor"),
        ReasonInfo(
            "colour_look_mismatch",
            "Colour / look not as shown",
            "unclear",
            None,
            "Unclear: vendor fabric or Dhaga photos",
        ),
        ReasonInfo("wrong_item", "Wrong item sent", "not_vendor", False, "Warehouse"),
        ReasonInfo("delivery_damage", "Damaged in delivery", "not_vendor", False, "Courier / packing"),
        ReasonInfo("changed_mind", "Changed mind", "not_vendor", False, "Customer"),
        ReasonInfo("other", "None of the above", "other", None, "No clear owner"),
    )
}

REASONS: tuple[str, ...] = tuple(REASON_INFO)
# Only these can be flagged against a vendor.
VENDOR_CAUSED: tuple[str, ...] = tuple(k for k, r in REASON_INFO.items() if r.vendor_caused)
# Shown per vendor (flagged or not): vendor-caused plus the unclear one.
VENDOR_TABLE_REASONS: tuple[str, ...] = tuple(
    k for k, r in REASON_INFO.items() if r.group in ("vendor", "unclear")
)
NOT_VENDOR: tuple[str, ...] = tuple(k for k, r in REASON_INFO.items() if r.group == "not_vendor")

FIT_DIRECTION_LABELS: dict[str, str] = {
    "runs_small": "Runs small",
    "runs_large": "Runs large",
    "length_wrong": "Length wrong",
    "area_specific": "Tight or loose in one area",
    "unclear": "Fit problem, direction unclear",
}

FIT_AREA_LABELS: dict[str, str] = {
    "shoulders": "Shoulders",
    "chest": "Chest",
    "waist": "Waist",
    "hips": "Hips",
    "sleeves": "Sleeves",
    "length": "Length",
    "other": "Other area",
}

CATEGORY_LABELS: dict[str, str] = {
    "womenswear": "Womenswear",
    "kidswear": "Kidswear",
    "mens": "Men's",
}
UNKNOWN_CATEGORY = "uncategorised"


def reason_label(reason: Optional[str]) -> str:
    info = REASON_INFO.get(reason or "")
    return info.label if info else (reason or "")


def category_label(category: Optional[str]) -> str:
    return CATEGORY_LABELS.get(category or "", "Uncategorised")
