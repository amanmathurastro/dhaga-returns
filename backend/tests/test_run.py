"""The whole chain (load -> filter -> classify -> aggregate -> brief) with fake models."""

from datetime import date

from app.pipeline.aggregate import Sale
from app.pipeline.brief import BriefInput
from app.pipeline.classify import LLMResult
from app.pipeline.run import RunDeps, RunInputs, process
from app.schemas import BriefClaim, VendorBrief
from tests.fakes import FakeClassifier, classification

VENDORS = [{"vendor_id": "V1", "name": "Jaipur Prints"}, {"vendor_id": "V2", "name": "Surat Silks"}]
SKUS = [
    {"sku_id": "W1", "vendor_id": "V1", "category": "womenswear"},
    {"sku_id": "W2", "vendor_id": "V2", "category": "womenswear"},
]
ORDER_LINES = [
    {"order_line_id": f"L{i}", "sku_id": "W1" if i <= 8 else "W2", "size": "M", "quantity": 1,
     "order_date": date(2026, 8, 1)}
    for i in range(1, 13)
]
SALES = [Sale("V1", "womenswear", "W1", 100), Sale("V2", "womenswear", "W2", 300)]


def ret(i, line, text, dropdown="Other"):
    return {"return_id": f"R{i:02d}", "order_line_id": line, "other_text": text,
            "return_date": date(2026, 8, 15), "dropdown_reason": dropdown}


RETURNS = (
    [ret(i, f"L{i}", "size bahut chhota hai") for i in range(1, 7)]  # 6 fit returns for V1
    + [
        ret(7, "L7", "call 9876543210, colour alag tha"),  # PII must be scrubbed before the model
        ret(8, "L8", "samajh nahi aaya kya likhu"),  # both models unsure
        ret(9, "L9", "size chhota"),  # 1 fit return for V2
        ret(10, "L10", "ok"),  # junk
        ret(11, None, "size chhota"),  # unmatched
        ret(12, "L12", "", dropdown="Size issue"),  # not "Other": out of scope
    ]
)


def fake_model(text):
    if "samajh" in text:
        return LLMResult(classification("other", 0.3), 100, 20)
    if "colour" in text:
        return LLMResult(classification("colour_look_mismatch", 0.9), 100, 20)
    return LLMResult(classification("fit", 0.9), 100, 20)


def good_brief(bi: BriefInput):
    return LLMResult(
        VendorBrief(
            vendor_id=bi.vendor_id,
            headline="Fit returns are well above the category average",
            claims=[BriefClaim(text="Fit returns are at this multiple of the average.",
                               metric_key="womenswear.fit_lift", value=bi.metrics["womenswear.fit_lift"])],
            example_comment_ids=[bi.comments[0].return_id],
            caveats=["Pattern only; the cause is not proven."],
        ),
        800, 120,
    )


def deps(a=fake_model, b=fake_model, writer=good_brief):
    return RunDeps(FakeClassifier(a), FakeClassifier(b), writer,
                   confidence_threshold=0.7, min_returns_to_flag=5, lift_threshold=2.0, concurrency=4)


def run(d=None, **kw):
    inputs = RunInputs(RETURNS, ORDER_LINES, SKUS, VENDORS, SALES)
    return process(inputs, d or deps(), **kw)


def test_every_other_return_ends_in_exactly_one_bucket():
    out = run()
    by_id = {c["return_id"]: c for c in out.classifications}
    assert len(by_id) == 11  # R12 (dropdown reason) is not analysed
    assert out.counts["processed"] == 11
    assert out.counts["classified"] == 8
    assert out.counts["junk"] == 1 and by_id["R10"]["error"] == "filler"
    assert out.counts["unmatched"] == 1 and "no order line" in by_id["R11"]["error"]
    assert out.counts["unclassified"] == 1 and by_id["R08"]["status"] == "unclassified"
    assert out.counts["routed"] == 1
    assert out.counts["dropdown_not_analysed"] == 1
    assert by_id["R01"] | {"error": None} == by_id["R01"]
    assert (by_id["R01"]["reason"], by_id["R01"]["fit_direction"], by_id["R01"]["model_used"]) == ("fit", "runs_small", "A")


def test_junk_and_unmatched_are_never_sent_to_a_model_and_pii_is_scrubbed():
    d = deps()
    run(d)
    sent = d.classifier_a.calls
    assert len(sent) == 9
    assert "ok" not in sent
    assert "call [phone], colour alag tha" in sent
    assert not any("9876543210" in text for text in sent)
    assert d.classifier_b.calls == ["samajh nahi aaya kya likhu"]


def test_flagged_vendor_gets_a_checked_brief():
    out = run()
    # V1: 6 fit / 100 = 0.06. Category: 7 / 400 = 0.0175. Lift 3.43 -> flagged. V2 is not.
    assert [b["vendor_id"] for b in out.briefs] == ["V1"]
    assert out.briefs[0]["status"] == "ok"
    assert out.briefs[0]["brief"]["claims"][0]["value"] == 3.43
    assert out.counts["briefs"] == {"ok": 1, "rejected_numbers_mismatch": 0, "failed": 0}
    assert out.counts["tokens"] == {"a_in": 900, "a_out": 180, "b_in": 100, "b_out": 20, "brief_in": 800, "brief_out": 120}


def test_brief_with_invented_number_is_rejected_but_the_run_still_finishes():
    def inventing(bi):
        brief = good_brief(bi).parsed
        return brief.model_copy(update={"headline": "Fit returns up 60%"})

    out = run(deps(writer=inventing))
    assert out.briefs[0]["status"] == "rejected_numbers_mismatch"
    assert out.counts["classified"] == 8


def test_models_down_means_everything_is_unclassified_not_a_crash():
    def down(_):
        raise TimeoutError("Request timed out")

    out = run(deps(a=down, b=down))
    assert out.counts["unclassified"] == 9 and out.counts["classified"] == 0
    assert out.counts["junk"] == 1 and out.counts["unmatched"] == 1
    assert out.briefs == []
    assert all("TimeoutError" in c["error"] for c in out.classifications if c["status"] == "unclassified")


def test_period_filters_on_order_date():
    out = run(period_start=date(2026, 9, 1))
    assert out.counts["processed"] == 0 and out.counts["outside_period"] == 11
    out = run(period_start=date(2026, 8, 1), period_end=date(2026, 8, 1))
    assert out.counts["processed"] == 10  # the unmatched one is dated by its return, 15 Aug
