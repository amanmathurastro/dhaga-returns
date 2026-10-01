"""Pydantic models: what the models must return, and what the API returns."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------
# Model output schemas (validated on every model call)
# --------------------------------------------------------------------------

Reason = Literal[
    "fit", "defect_quality", "colour_look_mismatch",
    "wrong_item", "delivery_damage", "changed_mind", "other",
]
FitDirection = Literal["runs_small", "runs_large", "length_wrong", "area_specific", "unclear"]
FitArea = Literal["shoulders", "chest", "waist", "hips", "sleeves", "length", "other"]


class ReturnClassification(BaseModel):
    reason: Reason
    fit_direction: Optional[FitDirection] = None
    fit_area: Optional[FitArea] = None
    secondary_reason: Optional[str] = None  # for multi-reason comments
    confidence: float = Field(ge=0, le=1)
    gist_en: str = Field(max_length=140)  # short English summary

    @model_validator(mode="after")
    def _fit_fields_only_for_fit(self):
        if self.reason != "fit" and (self.fit_direction is not None or self.fit_area is not None):
            raise ValueError("fit_direction and fit_area must be null unless reason is 'fit'")
        return self


class BriefClaim(BaseModel):
    text: str
    metric_key: str  # e.g. "womenswear.fit_rate", must exist in the vendor's metrics
    value: float  # must equal the computed value (checked in code)


class VendorBrief(BaseModel):
    vendor_id: str
    headline: str = Field(max_length=160)
    claims: list[BriefClaim]  # each claim cites a metric key
    example_comment_ids: list[str] = Field(max_length=5)  # real return IDs
    caveats: list[str]  # e.g. "small sample"


# --------------------------------------------------------------------------
# API models
# --------------------------------------------------------------------------


class ErrorOut(BaseModel):
    error: str
    message: str


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok", "unreachable"]
    openrouter_key_present: bool


class RunRequest(BaseModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must be on or before period_end")
        return self


class RunStarted(BaseModel):
    run_id: str


class RunInfo(BaseModel):
    run_id: str
    status: Literal["running", "done", "failed"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    model_a_id: Optional[str] = None
    model_b_id: Optional[str] = None
    counts: dict[str, Any] = {}
    cost_usd: Optional[float] = None
    error: Optional[str] = None


class RunList(BaseModel):
    runs: list[RunInfo]


class CoverageItem(BaseModel):
    key: Literal["classified", "junk", "unmatched", "unclassified"]
    label: str
    count: int
    share: Optional[float]


class ReasonCount(BaseModel):
    reason: str
    label: str
    group: Literal["vendor", "unclear", "not_vendor", "other"]
    likely_owner: str
    count: int
    share: Optional[float]  # of classified returns


class SummaryOut(BaseModel):
    run: RunInfo
    other_returns: int  # "Other" returns in the period (everything the pipeline looked at)
    dropdown_returns_not_analysed: int
    units_sold: int
    coverage: list[CoverageItem]
    reasons: list[ReasonCount]
    routed_to_model_b: int
    flagged_vendors: int


class CellOut(BaseModel):
    reason: str
    label: str
    can_flag: bool
    returns: int
    rate: Optional[float]
    category_avg: Optional[float]
    lift: Optional[float]
    flagged: bool


class VendorRow(BaseModel):
    vendor_id: str
    vendor_name: str
    city: Optional[str]
    category: str
    category_label: str
    units_sold: int
    returns_total: int
    cells: list[CellOut]
    flagged: bool


class Thresholds(BaseModel):
    min_returns_to_flag: int
    lift_threshold: float


class VendorsOut(BaseModel):
    run: RunInfo
    thresholds: Thresholds
    category: Optional[str]
    rows: list[VendorRow]
    unclassified: int  # > 0 means the table is partial
    unmatched: int


class LabelCount(BaseModel):
    key: str
    label: str
    count: int


class SkuOut(BaseModel):
    sku_id: str
    product_name: Optional[str]
    category_label: str
    is_live: Optional[bool]
    units_sold: int
    returns: int
    rate: Optional[float]
    top_reason_label: Optional[str]


class CommentOut(BaseModel):
    return_id: str
    text: str  # PII-scrubbed
    gist_en: Optional[str]
    reason: Optional[str]
    reason_label: Optional[str]
    fit_direction_label: Optional[str] = None
    secondary_reason: Optional[str] = None
    size: Optional[str] = None
    product_name: Optional[str] = None
    model_used: Optional[str] = None
    confidence: Optional[float] = None


class BriefOut(BaseModel):
    status: Literal["ok", "rejected_numbers_mismatch", "failed", "not_written"]
    brief: Optional[VendorBrief] = None
    problems: list[str] = []


class VendorDetailOut(BaseModel):
    run: RunInfo
    thresholds: Thresholds
    vendor_id: str
    vendor_name: str
    city: Optional[str]
    segments: list[VendorRow]
    fit_directions: list[LabelCount]
    fit_areas: list[LabelCount]
    top_skus: list[SkuOut]
    comments: list[CommentOut]
    comments_total: int
    brief: BriefOut


class NonVendorGroup(BaseModel):
    reason: str
    label: str
    likely_owner: str
    count: int
    share: Optional[float]  # of classified returns
    examples: list[CommentOut]


class NonVendorOut(BaseModel):
    run: RunInfo
    classified_total: int
    groups: list[NonVendorGroup]


class GapExample(BaseModel):
    return_id: str
    text: str  # PII-scrubbed
    why: Optional[str]
    order_line_id: Optional[str] = None


class GapBucket(BaseModel):
    key: Literal["unmatched", "junk", "unclassified"]
    label: str
    explainer: str
    count: int
    examples: list[GapExample]


class GapsOut(BaseModel):
    run: RunInfo
    total: int
    buckets: list[GapBucket]


class PreviewRequest(BaseModel):
    text: str = Field(max_length=2000)


class PreviewOut(BaseModel):
    status: Literal["classified", "junk", "unclassified"]
    scrubbed_text: str
    classification: Optional[ReturnClassification] = None
    reason_label: Optional[str] = None
    fit_direction_label: Optional[str] = None
    likely_owner: Optional[str] = None
    model_used: Literal["A", "B", "none"]
    routed: bool
    confidence_threshold: float
    detail: Optional[str] = None  # why it is junk, or why it could not be classified
