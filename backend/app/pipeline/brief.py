"""Vendor brief: Model B summarises a flagged vendor's pattern; code checks every number.

Two halves, like classify.py.

1. THE LANGCHAIN HALF: `BRIEF_SYSTEM_PROMPT`, `render_input` and `build_brief_writer`.

2. THE CHECKING HALF: plain Python, tested in tests/test_brief.py.

The contract between the two halves
-----------------------------------
A brief writer is a function:   (BriefInput) -> LLMResult[VendorBrief]

  - If the model call fails or the output does not fit the schema: RAISE.
    `write_brief` turns that into status "failed", shown on the page.
  - The numbers the model may use are exactly `BriefInput.metrics`
    (a flat dict, already rounded). `check_brief` rejects the brief unless:
      * every claim's `metric_key` is a key of `metrics`
      * every claim's `value` equals `metrics[metric_key]`
      * every number written in a claim's text is that claim's value
        (as given, or as a percentage, e.g. 0.0842 -> "8.4%" or "8.42%")
      * every number in the headline / caveats is some value from `metrics`
      * `vendor_id` matches and `example_comment_ids` are IDs from
        `BriefInput.comments` (max 5)
    So the prompt tells the model: one number per claim, copied from the
    metrics, and no arithmetic of its own.

Metric keys look like "<category>.<name>", for example:
    womenswear.units_sold
    womenswear.fit_returns        womenswear.fit_rate
    womenswear.fit_category_avg   womenswear.fit_lift
    womenswear.fit_runs_small_returns
Rates and averages are fractions (0.0842 = 8.42%). Lift is a multiple (3.1 = 3.1x).
"""

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Optional

from app.pipeline.aggregate import Segment
from app.pipeline.classify import LLMResult, _short, make_model, structured_call
from app.schemas import VendorBrief
from app.taxonomy import VENDOR_TABLE_REASONS

BRIEF_MAX_COMMENTS = 40


@dataclass(frozen=True)
class BriefComment:
    return_id: str
    text: str  # PII-scrubbed original comment
    gist_en: str
    reason: str
    fit_direction: Optional[str] = None


@dataclass(frozen=True)
class BriefInput:
    vendor_id: str
    vendor_name: str
    metrics: dict[str, float]
    flagged_metric_keys: list[str]  # the "<category>.<reason>_lift" keys that tripped a flag
    comments: list[BriefComment]


BriefWriter = Callable[[BriefInput], LLMResult[VendorBrief]]


# ==========================================================================
# 1. LANGCHAIN HALF
# ==========================================================================

# The number rules below mirror `check_brief`. If one changes, change the other.
BRIEF_SYSTEM_PROMPT = """\
You write a short internal brief about one vendor for Neha, Category Head at Dhaga & Co., an Indian online fashion marketplace. She uses it to decide whether to raise returns with the vendor. It is never shown to the vendor or to customers.

You are given the vendor, a list of metrics computed by code, which of them were flagged, and customer return comments for that vendor.

Describe the pattern. Do not explain it.
- Say what is coming back, how much, and how that compares with the category average.
- Never state or suggest a cause: nothing like "because of their size chart", "poor quality control", "likely a cutting issue". The data does not show causes.
- Plain language, no jargon. Write "2.9 times the category average", never "lift".

What the metric names mean ("<category>." comes first, for example "womenswear."):
- units_sold                 units of this vendor's products sold in the category
- <reason>_returns           number of returns for that reason
- <reason>_rate              returns for that reason divided by units sold, as a fraction (0.1172 means 11.72%)
- <reason>_category_avg      the same rate across every vendor in the category, as a fraction
- <reason>_lift              the vendor's rate divided by the category average (2.92 means 2.92 times the average)
- fit_<direction>_returns    number of fit returns of that kind (runs_small, runs_large, ...)

Numbers. Code checks every digit you write and throws the whole brief away on any mismatch.
- claims: 2 to 5. Each claim is about exactly one metric: put its name in metric_key and copy its value into value exactly as given.
- A claim's text may contain that one number and no other. Write it as given, or rounded, or for a rate as a percentage ("11.7%" for 0.1172). No second number, no arithmetic, no totals or differences you worked out yourself.
- headline: at most one number, and it must be one of the metric values (rounding or a percentage is fine).
- caveats: write them without digits.
- Write no other digits anywhere: no clothing sizes, dates, return IDs or counts of comments in the text. Say "a larger size", not the size.

Other fields:
- headline: the main flagged pattern in one sentence, at most 150 characters.
- caveats: always say that this is a pattern and the cause is not known. If a claim rests on few returns, say the sample is small. Add any other honest limit you see in the comments.
- example_comment_ids: up to 5 return IDs from the comments given, chosen because they show the flagged pattern. Only IDs from the list.
- vendor_id: copy it exactly as given.
"""


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


def render_input(brief_input: BriefInput) -> str:
    """The human message for one vendor: plain text, one fact per line."""
    lines = [
        f"Vendor: {brief_input.vendor_name}",
        f"vendor_id: {brief_input.vendor_id}",
        "",
        "Flagged metrics (well above the category average, with enough returns to matter):",
        *(f"- {key}" for key in brief_input.flagged_metric_keys),
        "",
        "Metrics (the only numbers you may use):",
        *(f"- {key} = {_number(value)}" for key, value in brief_input.metrics.items()),
        "",
        "Customer return comments (return ID | reason | kind of fit problem | customer's words | English gist):",
        *(
            f"- {c.return_id} | {c.reason} | {c.fit_direction or '-'} | {c.text} | {c.gist_en}"
            for c in brief_input.comments
        ),
    ]
    return "\n".join(lines)


def build_brief_writer(model_id: str) -> BriefWriter:
    """A brief writer (built once per run, with MODEL_B_ID).

    Temperature 0.2: a little freedom in wording. The output is internal and every number is checked by code.
    """
    call = structured_call(make_model(model_id, temperature=0.2), VendorBrief, BRIEF_SYSTEM_PROMPT)

    def write(brief_input: BriefInput) -> LLMResult[VendorBrief]:
        return call(render_input(brief_input))

    return write


# ==========================================================================
# 2. CHECKING HALF
# ==========================================================================


def vendor_metrics(segments: Iterable[Segment]) -> dict[str, float]:
    """The flat, rounded numbers a brief may cite. This is 'the table'."""
    metrics: dict[str, float] = {}
    for seg in segments:
        p = seg.category
        metrics[f"{p}.units_sold"] = float(seg.units_sold)
        for reason in VENDOR_TABLE_REASONS:
            cell = seg.cells[reason]
            metrics[f"{p}.{reason}_returns"] = float(cell.returns)
            if cell.rate is not None:
                metrics[f"{p}.{reason}_rate"] = round(cell.rate, 4)
            if cell.category_avg is not None:
                metrics[f"{p}.{reason}_category_avg"] = round(cell.category_avg, 4)
            if cell.lift is not None:
                metrics[f"{p}.{reason}_lift"] = round(cell.lift, 2)
        for direction, n in sorted(seg.fit_directions.items()):
            metrics[f"{p}.fit_{direction}_returns"] = float(n)
    return metrics


def flagged_keys(segments: Iterable[Segment]) -> list[str]:
    return [
        f"{seg.category}.{cell.reason}_lift"
        for seg in segments
        for cell in seg.cells.values()
        if cell.flagged
    ]


_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_TOLERANCE = 1e-6


def _numbers_in(text: str) -> list[float]:
    return [float(m.group().replace(",", "")) for m in _NUMBER.finditer(text or "")]


def _renderings(value: float) -> set[float]:
    """Ways a metric may legitimately be written: as is, or as a percentage, rounded."""
    as_is = {round(value, k) for k in range(0, 5)}
    as_percent = {round(value * 100, k) for k in range(0, 3)}
    return as_is | as_percent


def _matches(number: float, values: Iterable[float]) -> bool:
    return any(abs(number - r) <= _TOLERANCE for v in values for r in _renderings(v))


@dataclass
class BriefProblems:
    numbers: list[str]  # invented or mismatched numbers
    other: list[str]  # wrong vendor, unknown comment IDs

    @property
    def any(self) -> bool:
        return bool(self.numbers or self.other)


def check_brief(brief: VendorBrief, brief_input: BriefInput) -> BriefProblems:
    metrics = brief_input.metrics
    numbers: list[str] = []
    other: list[str] = []

    if brief.vendor_id != brief_input.vendor_id:
        other.append(f"Brief is for vendor '{brief.vendor_id}', expected '{brief_input.vendor_id}'")

    for claim in brief.claims:
        if claim.metric_key not in metrics:
            numbers.append(f"Claim cites '{claim.metric_key}', which is not in the vendor's table")
            continue
        expected = metrics[claim.metric_key]
        if abs(claim.value - expected) > _TOLERANCE:
            numbers.append(f"Claim says {claim.metric_key} = {claim.value}, the table says {expected}")
            continue
        for n in _numbers_in(claim.text):
            if not _matches(n, [expected]):
                numbers.append(f"Claim text contains {n:g}, which is not its cited value ({expected:g})")

    for where, text in [("Headline", brief.headline)] + [("Caveat", c) for c in brief.caveats]:
        for n in _numbers_in(text):
            if not _matches(n, metrics.values()):
                numbers.append(f"{where} contains {n:g}, which is not in the vendor's table")

    known_ids = {c.return_id for c in brief_input.comments}
    unknown = [i for i in brief.example_comment_ids if i not in known_ids]
    if unknown:
        other.append("Brief cites comments that do not exist for this vendor: " + ", ".join(unknown))

    return BriefProblems(numbers, other)


@dataclass
class BriefOutcome:
    vendor_id: str
    status: Literal["ok", "rejected_numbers_mismatch", "failed"]
    brief: Optional[VendorBrief] = None
    problems: Optional[list[str]] = None
    input_tokens: int = 0
    output_tokens: int = 0

    def to_json(self) -> dict:
        """What is stored in vendor_briefs.brief."""
        if self.status == "ok":
            return self.brief.model_dump()
        stored: dict = {"problems": self.problems or []}
        if self.brief is not None:
            stored["rejected_brief"] = self.brief.model_dump()  # kept for debugging, never shown
        return stored


def write_brief(brief_input: BriefInput, writer: BriefWriter) -> BriefOutcome:
    """Call the writer and check its output. Never raises."""
    vendor_id = brief_input.vendor_id
    try:
        result = writer(brief_input)
        if isinstance(result, LLMResult):
            parsed, tokens_in, tokens_out = result.parsed, result.input_tokens, result.output_tokens
        else:
            parsed, tokens_in, tokens_out = result, 0, 0
        if parsed is None:
            return BriefOutcome(vendor_id, "failed", problems=["Model returned nothing"])
        brief = VendorBrief.model_validate(parsed.model_dump() if isinstance(parsed, VendorBrief) else parsed)
    except Exception as exc:
        return BriefOutcome(vendor_id, "failed", problems=[_short(exc)])

    tokens = dict(input_tokens=int(tokens_in or 0), output_tokens=int(tokens_out or 0))
    problems = check_brief(brief, brief_input)
    if problems.numbers:
        return BriefOutcome(
            vendor_id, "rejected_numbers_mismatch", brief, problems.numbers + problems.other, **tokens
        )
    if problems.other:
        return BriefOutcome(vendor_id, "failed", brief, problems.other, **tokens)
    return BriefOutcome(vendor_id, "ok", brief, **tokens)
