"""The LangChain half, run for real against a fake chat model (no OpenRouter call).

The fake stands in for the model only. The prompt, the tool-call parsing, the
schema validation and the token counting are the real chain.
"""

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app import config
from app.pipeline import brief as brief_mod
from app.pipeline import classify as classify_mod
from app.pipeline.brief import BRIEF_SYSTEM_PROMPT, BriefComment, BriefInput, render_input, write_brief
from app.pipeline.classify import CLASSIFY_SYSTEM_PROMPT, route, structured_call
from app.schemas import ReturnClassification, VendorBrief


class FakeChatModel(BaseChatModel):
    """Answers every call with the given tool-call arguments (or plain text if None)."""

    tool_name: str = "ReturnClassification"
    args: Any = None
    error: Any = None
    seen: list = []
    bound: list = []

    @property
    def _llm_type(self) -> str:
        return "fake"

    def bind_tools(self, tools, **kwargs):
        self.bound.append((tools, kwargs))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        if self.error is not None:
            raise self.error
        tool_calls = [] if self.args is None else [{"name": self.tool_name, "args": self.args, "id": "call_1"}]
        message = AIMessage(
            content="" if tool_calls else "I think this is about fit.",
            tool_calls=tool_calls,
            usage_metadata={"input_tokens": 812, "output_tokens": 47, "total_tokens": 859},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def fake(args=None, **kw) -> FakeChatModel:
    return FakeChatModel(args=args, seen=[], bound=[], **kw)


FIT = {"reason": "fit", "fit_direction": "runs_small", "confidence": 0.93, "gist_en": "Kurta is smaller than size L"}


def classifier(model):
    return structured_call(model, ReturnClassification, CLASSIFY_SYSTEM_PROMPT)


def test_valid_answer_is_parsed_with_token_counts():
    result = classifier(fake(FIT))("size chhota hai")
    assert isinstance(result.parsed, ReturnClassification)
    assert (result.parsed.reason, result.parsed.fit_direction, result.parsed.confidence) == ("fit", "runs_small", 0.93)
    assert (result.input_tokens, result.output_tokens) == (812, 47)


def test_model_receives_the_system_prompt_and_the_comment_untouched():
    model = fake(FIT)
    comment = "size {chhota} hai, call [phone]"  # braces must not be treated as template variables
    classifier(model)(comment)
    system, human = model.seen[0]
    assert system.type == "system" and system.content == CLASSIFY_SYSTEM_PROMPT
    assert human.type == "human" and human.content == comment


def test_schema_is_bound_as_a_forced_tool_call():
    model = fake(FIT)
    classifier(model)
    tools, kwargs = model.bound[0]
    assert tools == [ReturnClassification] and kwargs["tool_choice"] == "any"


@pytest.mark.parametrize(
    "bad",
    [
        {"reason": "too_expensive", "confidence": 0.9, "gist_en": "x"},
        {"reason": "defect_quality", "fit_direction": "runs_small", "confidence": 0.9, "gist_en": "x"},
        {"reason": "fit", "confidence": 1.4, "gist_en": "x"},
        {"reason": "fit", "confidence": 0.9, "gist_en": "x" * 141},
        {"reason": "fit"},
    ],
)
def test_output_that_does_not_fit_the_schema_raises(bad):
    with pytest.raises(Exception):
        classifier(fake(bad))("size chhota hai")


def test_plain_text_answer_without_a_tool_call_raises():
    with pytest.raises(ValueError, match="structured answer"):
        classifier(fake(None))("size chhota hai")


def test_model_error_propagates():
    with pytest.raises(TimeoutError):
        classifier(fake(FIT, error=TimeoutError("Request timed out")))("size chhota hai")


def test_real_chain_plugs_into_routing():
    unsure = classifier(fake({"reason": "other", "confidence": 0.3, "gist_en": "Unclear"}))
    broken = classifier(fake({"reason": "nonsense"}))
    good = classifier(fake(FIT))

    assert route("x", good, broken, 0.7).model_used == "A"
    assert route("x", unsure, good, 0.7).model_used == "B"
    via_b = route("x", broken, good, 0.7)
    assert via_b.model_used == "B" and not via_b.attempts[0].valid
    assert [(a.input_tokens, a.output_tokens) for a in via_b.attempts] == [(0, 0), (812, 47)]
    assert route("x", broken, unsure, 0.7).status == "unclassified"


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setitem(config.Settings.model_config, "env_file", None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    config._load.cache_clear()
    yield
    config._load.cache_clear()


def test_make_model_points_at_openrouter(settings, monkeypatch):
    model = classify_mod.make_model("vendor/some-model", 0.2)
    assert model.model_name == "vendor/some-model" and model.temperature == 0.2
    assert model.openai_api_base == "https://openrouter.ai/api/v1"
    assert model.openai_api_key.get_secret_value() == "sk-or-test"
    assert model.request_timeout == 30 and model.max_retries == 2


def test_temperatures(monkeypatch):
    made = []

    def spy(model_id, temperature):
        made.append((model_id, temperature))
        return fake(FIT)

    monkeypatch.setattr(classify_mod, "make_model", spy)
    monkeypatch.setattr(brief_mod, "make_model", spy)
    classify_mod.build_classifier("a/model")
    brief_mod.build_brief_writer("b/model")
    assert made == [("a/model", 0.0), ("b/model", 0.2)]


BRIEF_INPUT = BriefInput(
    vendor_id="V01",
    vendor_name="Jaipur Block Prints",
    metrics={
        "womenswear.units_sold": 145.0,
        "womenswear.fit_returns": 17.0,
        "womenswear.fit_rate": 0.1172,
        "womenswear.fit_category_avg": 0.0402,
        "womenswear.fit_lift": 2.92,
    },
    flagged_metric_keys=["womenswear.fit_lift"],
    comments=[BriefComment("RET-0006", "Runs very small {sic}", "Runs small", "fit", "runs_small")],
)
GOOD_BRIEF = {
    "vendor_id": "V01",
    "headline": "Fit returns are 2.9 times the womenswear average",
    "claims": [
        {"text": "11.7% of units sold came back for fit.", "metric_key": "womenswear.fit_rate", "value": 0.1172},
        {"text": "That is 2.92 times the category average.", "metric_key": "womenswear.fit_lift", "value": 2.92},
    ],
    "example_comment_ids": ["RET-0006"],
    "caveats": ["This is a pattern; the cause is not known."],
}


def brief_writer(model, monkeypatch):
    monkeypatch.setattr(brief_mod, "make_model", lambda model_id, temperature: model)
    return brief_mod.build_brief_writer("b/model")


def test_render_input_gives_the_model_every_metric_and_comment():
    text = render_input(BRIEF_INPUT)
    assert "vendor_id: V01" in text and "Vendor: Jaipur Block Prints" in text
    assert "- womenswear.units_sold = 145" in text  # counts without a trailing .0
    assert "- womenswear.fit_rate = 0.1172" in text
    assert "- womenswear.fit_lift = 2.92" in text
    assert "- RET-0006 | fit | runs_small | Runs very small {sic} | Runs small" in text


def test_brief_writer_end_to_end_passes_the_number_check(monkeypatch):
    model = fake(GOOD_BRIEF, tool_name="VendorBrief")
    outcome = write_brief(BRIEF_INPUT, brief_writer(model, monkeypatch))
    assert outcome.status == "ok" and isinstance(outcome.brief, VendorBrief)
    assert (outcome.input_tokens, outcome.output_tokens) == (812, 47)
    system, human = model.seen[0]
    assert system.content == BRIEF_SYSTEM_PROMPT and human.content == render_input(BRIEF_INPUT)


def test_brief_with_an_invented_number_is_rejected(monkeypatch):
    bad = {**GOOD_BRIEF, "headline": "Fit returns have doubled to 40%"}
    outcome = write_brief(BRIEF_INPUT, brief_writer(fake(bad, tool_name="VendorBrief"), monkeypatch))
    assert outcome.status == "rejected_numbers_mismatch"


def test_brief_that_does_not_fit_the_schema_fails_visibly(monkeypatch):
    bad = {**GOOD_BRIEF, "example_comment_ids": ["RET-0006"] * 6}
    outcome = write_brief(BRIEF_INPUT, brief_writer(fake(bad, tool_name="VendorBrief"), monkeypatch))
    assert outcome.status == "failed" and outcome.problems
