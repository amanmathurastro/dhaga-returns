"""The brief's numbers are checked against the table. A mismatch rejects the brief."""

import pytest

from app.pipeline.aggregate import ClassifiedReturn, Sale, aggregate
from app.pipeline.brief import (
    BriefComment, BriefInput, check_brief, flagged_keys, vendor_metrics, write_brief,
)
from app.pipeline.classify import LLMResult
from app.schemas import BriefClaim, VendorBrief

METRICS = {
    "womenswear.units_sold": 1240.0,
    "womenswear.fit_returns": 42.0,
    "womenswear.fit_rate": 0.0339,
    "womenswear.fit_category_avg": 0.0109,
    "womenswear.fit_lift": 3.11,
    "womenswear.fit_runs_small_returns": 35.0,
}
INPUT = BriefInput(
    vendor_id="V1",
    vendor_name="Jaipur Prints",
    metrics=METRICS,
    flagged_metric_keys=["womenswear.fit_lift"],
    comments=[BriefComment("R1", "size chhota", "Runs small", "fit", "runs_small"),
              BriefComment("R2", "tight hai", "Too tight", "fit", "runs_small")],
)


def brief(**overrides) -> VendorBrief:
    fields = dict(
        vendor_id="V1",
        headline="Fit returns are 3.1x the womenswear average",
        claims=[
            BriefClaim(text="Fit returns run at 3.11x the category average.", metric_key="womenswear.fit_lift", value=3.11),
            BriefClaim(text="3.4% of units sold came back for fit.", metric_key="womenswear.fit_rate", value=0.0339),
            BriefClaim(text="35 of those returns say the item runs small.", metric_key="womenswear.fit_runs_small_returns", value=35),
            BriefClaim(text="Based on 1,240 units sold.", metric_key="womenswear.units_sold", value=1240),
        ],
        example_comment_ids=["R1", "R2"],
        caveats=["This is a pattern, not a proven cause.", "Only 42 fit returns so far."],
    )
    fields.update(overrides)
    return VendorBrief(**fields)


def writer(result):
    def write(_):
        if isinstance(result, BaseException):
            raise result
        return result
    return write


def test_brief_with_matching_numbers_is_ok():
    outcome = write_brief(INPUT, writer(LLMResult(brief(), 900, 150)))
    assert outcome.status == "ok" and outcome.problems is None
    assert (outcome.input_tokens, outcome.output_tokens) == (900, 150)
    assert outcome.to_json()["headline"].startswith("Fit returns")


def test_claim_value_that_differs_from_the_table_is_rejected():
    bad = brief(claims=[BriefClaim(text="Fit returns run at 4.2x the average.", metric_key="womenswear.fit_lift", value=4.2)])
    outcome = write_brief(INPUT, writer(LLMResult(bad)))
    assert outcome.status == "rejected_numbers_mismatch"
    assert "the table says 3.11" in outcome.problems[0]


def test_claim_citing_an_unknown_metric_is_rejected():
    bad = brief(claims=[BriefClaim(text="Defects are high.", metric_key="womenswear.torn_rate", value=0.2)])
    assert write_brief(INPUT, writer(bad)).status == "rejected_numbers_mismatch"


def test_number_in_claim_text_must_be_the_cited_value():
    # The structured value is right, but the sentence says something else.
    bad = brief(claims=[BriefClaim(text="Fit returns run at 5x the category average.", metric_key="womenswear.fit_lift", value=3.11)])
    outcome = write_brief(INPUT, writer(bad))
    assert outcome.status == "rejected_numbers_mismatch"
    assert "Claim text contains 5" in outcome.problems[0]


def test_invented_number_in_headline_or_caveat_is_rejected():
    assert write_brief(INPUT, writer(brief(headline="Fit returns up 60% this month"))).status == "rejected_numbers_mismatch"
    assert write_brief(INPUT, writer(brief(caveats=["Only 7 returns."]))).status == "rejected_numbers_mismatch"


@pytest.mark.parametrize("text", ["3.39% of units", "3.4% of units", "3% of units", "a rate of 0.0339", "0.034 of units"])
def test_a_rate_may_be_written_as_a_fraction_or_a_rounded_percentage(text):
    ok = brief(claims=[BriefClaim(text=text, metric_key="womenswear.fit_rate", value=0.0339)])
    assert write_brief(INPUT, writer(ok)).status == "ok"


def test_rejected_brief_text_is_stored_for_debugging_only():
    bad = brief(headline="Returns up 60%")
    stored = write_brief(INPUT, writer(bad)).to_json()
    assert set(stored) == {"problems", "rejected_brief"}


def test_unknown_example_comment_or_wrong_vendor_fails():
    made_up = write_brief(INPUT, writer(brief(example_comment_ids=["R1", "R999"])))
    assert made_up.status == "failed" and "R999" in made_up.problems[0]
    assert write_brief(INPUT, writer(brief(vendor_id="V2"))).status == "failed"


def test_model_error_or_bad_schema_fails_visibly():
    timeout = write_brief(INPUT, writer(TimeoutError("timed out")))
    assert timeout.status == "failed" and "TimeoutError" in timeout.problems[0]
    assert write_brief(INPUT, writer(None)).status == "failed"
    too_many = {**brief().model_dump(), "example_comment_ids": ["R1"] * 6}
    assert write_brief(INPUT, writer(too_many)).status == "failed"


def test_metrics_come_from_the_same_segments_as_the_table():
    sales = [Sale("V1", "womenswear", "W1", 100), Sale("V2", "womenswear", "W2", 300)]
    returns = [ClassifiedReturn(f"R{i}", "V1", "womenswear", "W1", "fit", "runs_small") for i in range(12)]
    returns += [ClassifiedReturn(f"Q{i}", "V2", "womenswear", "W2", "fit", "runs_large") for i in range(4)]
    v1 = [s for s in aggregate(sales, returns, min_returns_to_flag=5, lift_threshold=2.0) if s.vendor_id == "V1"]

    metrics = vendor_metrics(v1)
    assert metrics["womenswear.units_sold"] == 100
    assert metrics["womenswear.fit_returns"] == 12
    assert metrics["womenswear.fit_rate"] == 0.12
    assert metrics["womenswear.fit_category_avg"] == 0.04
    assert metrics["womenswear.fit_lift"] == 3.0
    assert metrics["womenswear.fit_runs_small_returns"] == 12
    assert "womenswear.changed_mind_rate" not in metrics  # not a vendor matter
    assert flagged_keys(v1) == ["womenswear.fit_lift"]


def test_check_brief_reports_every_problem():
    bad = brief(vendor_id="V2", headline="Up 60%", example_comment_ids=["R999"])
    problems = check_brief(bad, INPUT)
    assert len(problems.numbers) == 1 and len(problems.other) == 2
