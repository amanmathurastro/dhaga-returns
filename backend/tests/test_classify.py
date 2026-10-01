"""Routing logic with mocked models: valid, low confidence, invalid schema, timeout."""

import pytest
from pydantic import ValidationError

from app.pipeline.classify import LLMResult, route, safe_build
from app.schemas import ReturnClassification
from tests.fakes import FakeClassifier, answers, classification

THRESHOLD = 0.7


def test_confident_valid_answer_from_a_never_calls_b():
    a, b = answers("fit", 0.9), answers("defect_quality", 0.99)
    result = route("size chhota", a, b, THRESHOLD)
    assert result.status == "classified" and result.model_used == "A" and not result.routed
    assert result.classification.reason == "fit"
    assert a.calls == ["size chhota"] and b.calls == []


def test_confidence_exactly_at_threshold_is_accepted():
    result = route("x", answers("fit", THRESHOLD), answers(), THRESHOLD)
    assert result.model_used == "A"


def test_low_confidence_routes_to_b():
    a, b = answers("other", 0.4), answers("defect_quality", 0.85)
    result = route("silai khul gayi", a, b, THRESHOLD)
    assert result.status == "classified" and result.model_used == "B" and result.routed
    assert result.classification.reason == "defect_quality"
    assert b.calls == ["silai khul gayi"]


def test_invalid_schema_routes_to_b():
    # What a model might send back: fit fields on a non-fit reason, and an unknown reason.
    bad_outputs = [
        {"reason": "defect_quality", "fit_direction": "runs_small", "confidence": 0.9, "gist_en": "x"},
        {"reason": "too_expensive", "confidence": 0.9, "gist_en": "x"},
        {"reason": "fit", "confidence": 1.7, "gist_en": "x"},
        {"reason": "fit", "confidence": 0.9, "gist_en": "x" * 141},
        None,
    ]
    for bad in bad_outputs:
        result = route("x", FakeClassifier(bad), answers("fit", 0.9), THRESHOLD)
        assert result.model_used == "B", bad
        assert not result.attempts[0].valid


def test_timeout_routes_to_b():
    result = route("x", FakeClassifier(TimeoutError("Request timed out")), answers("fit", 0.9), THRESHOLD)
    assert result.status == "classified" and result.model_used == "B"
    assert "TimeoutError" in result.attempts[0].error


def test_both_models_unsure_is_unclassified_not_a_guess():
    result = route("hmm theek nahi", answers("other", 0.3), answers("fit", 0.5), THRESHOLD)
    assert result.status == "unclassified"
    assert result.classification is None and result.model_used == "none" and result.routed
    assert "Model A was unsure (confidence 0.30" in result.error
    assert "Model B was unsure (confidence 0.50" in result.error


def test_both_models_failing_is_unclassified_with_the_errors_kept():
    result = route("x", FakeClassifier(TimeoutError("timed out")), FakeClassifier(RuntimeError("502 Bad Gateway")), THRESHOLD)
    assert result.status == "unclassified"
    assert "Model A failed: TimeoutError: timed out" in result.error
    assert "Model B failed: RuntimeError: 502 Bad Gateway" in result.error


def test_route_never_raises_and_error_text_stays_short():
    result = route("x", FakeClassifier(RuntimeError("boom " * 500)), FakeClassifier(KeyError("k")), THRESHOLD)
    assert result.status == "unclassified"
    assert len(result.error) < 600


def test_token_counts_are_kept_per_attempt():
    result = route("x", answers("fit", 0.2, tokens=(120, 30)), answers("fit", 0.9, tokens=(150, 40)), THRESHOLD)
    assert [(a.model, a.input_tokens, a.output_tokens) for a in result.attempts] == [("A", 120, 30), ("B", 150, 40)]


def test_classifier_may_return_a_bare_classification_or_dict():
    bare = route("x", FakeClassifier(classification("fit", 0.9)), answers(), THRESHOLD)
    as_dict = route("x", FakeClassifier({"reason": "changed_mind", "confidence": 0.9, "gist_en": "g"}), answers(), THRESHOLD)
    assert bare.model_used == "A" and as_dict.classification.reason == "changed_mind"


def test_schema_rejects_fit_fields_on_other_reasons():
    with pytest.raises(ValidationError):
        ReturnClassification(reason="wrong_item", fit_direction="runs_small", confidence=0.9, gist_en="g")
    with pytest.raises(ValidationError):
        ReturnClassification(reason="wrong_item", fit_area="waist", confidence=0.9, gist_en="g")
    ok = ReturnClassification(reason="fit", fit_direction="area_specific", fit_area="waist", confidence=0.9, gist_en="g")
    assert ok.fit_area == "waist"


def test_safe_build_turns_a_broken_builder_into_per_call_failures():
    def broken_builder(model_id):
        raise NotImplementedError("Model step not written yet")

    classifier = safe_build(broken_builder, "some/model")
    result = route("x", classifier, classifier, THRESHOLD)
    assert result.status == "unclassified"
    assert "Model step not written yet" in result.error


def test_working_builder_passes_through_safe_build():
    built = safe_build(lambda model_id: answers("fit", 0.9), "some/model")
    assert isinstance(built("x"), LLMResult)

