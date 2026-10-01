"""Classify one return comment: Model A first, Model B for the hard cases.

This file has two halves.

1. THE LANGCHAIN HALF: `make_model`, `CLASSIFY_SYSTEM_PROMPT`, `structured_call`
   and `build_classifier`. This is the only place a classification model is called.

2. THE ROUTING HALF: plain Python, tested with fake models in
   tests/test_classify.py. It only relies on the contract below.

The contract between the two halves
-----------------------------------
A classifier is a function:   (scrubbed_text: str) -> LLMResult[ReturnClassification]

  - It receives text that has ALREADY been PII-scrubbed and junk-filtered.
  - It returns `LLMResult(parsed=<ReturnClassification>, input_tokens=..., output_tokens=...)`.
  - If the model call fails, times out, or returns something that does not fit
    the schema, it RAISES. The routing below treats any exception as "invalid"
    and moves on to Model B.
  - It is safe to call from several threads at once (run.py does).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Literal, Optional, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.schemas import ReturnClassification

T = TypeVar("T")


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    input_tokens: int = 0
    output_tokens: int = 0


Classifier = Callable[[str], LLMResult[ReturnClassification]]


# ==========================================================================
# 1. LANGCHAIN HALF
# ==========================================================================

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# The output shape is sent to the model as a tool schema by `with_structured_output`,
# so this prompt only describes the judgment. Who is at fault (vendor / courier /
# customer) is deliberately not asked: that mapping lives in app/taxonomy.py.
CLASSIFY_SYSTEM_PROMPT = """\
You classify one customer return comment from Dhaga & Co., an Indian online fashion marketplace (kurtas, sarees, kidswear, menswear).

The comment is what the customer typed after choosing "Other" as their return reason. It may be Hinglish (Hindi in Latin letters), Hindi in Devanagari, English, or a mix, with typos and SMS-style shortening ("bht choti h", "nhi", "jbki"). Read it as written. "[phone]" and "[email]" are placeholders where personal details were removed; ignore them.

Pick the ONE main reason the item is being returned.

fit
  The size or fit is wrong: too small, too big, tight, loose, too short, too long. This includes "ordered my usual size per the size chart but it is small".
  Also fill fit_direction:
    runs_small     the whole garment is smaller or tighter than the size ordered
    runs_large     the whole garment is bigger or looser than the size ordered
    length_wrong   the complaint is only about length (too long or too short)
    area_specific  it is tight or loose in one named place; then also fill fit_area (shoulders, chest, waist, hips, sleeves, length, other)
    unclear        a fit problem, but the comment does not say which way
defect_quality
  Something is wrong with the product as it was made: stitching coming apart, a hole, a broken zip or button, loose threads, shrinking or colour running after a wash, fabric that is itchy, too thin or poor quality.
colour_look_mismatch
  The product is not broken, but it does not look like the photos or listing: different colour or shade, different print, different fabric than shown.
wrong_item
  A different product, colour or size than the one ordered was sent ("green order ki thi, blue bhej di", "tag pe XL hai, maine L manga tha").
delivery_damage
  The damage happened in packing or transit: torn or opened packet, item dirty or stained from a damaged parcel.
changed_mind
  Nothing is claimed to be wrong with the product: did not like it, no longer needed, found it cheaper elsewhere, the person it was bought for did not want it.
other
  A real reason that fits none of the above (late delivery, duplicate order), or the comment gives no reason at all (for example it only asks for a refund).

Borders that are easy to get wrong:
- "silai khul gayi" (stitching came apart) is defect_quality, not fit.
- "L manga tha, label pe L hi hai par chhota hai" is fit (right size sent, it runs small). "L manga tha, XL bhej diya" is wrong_item (a different size was sent).
- "ek wash me colour nikal gaya" is defect_quality. "photo me maroon tha, laal aaya" is colour_look_mismatch.
- "packet phata hua aaya" is delivery_damage. "kurta phata hua tha" with no mention of the parcel is defect_quality.
- "pasand nahi aaya" with no fault mentioned is changed_mind. Use other only when a different, real reason is given or none at all.
- Sarcasm: classify the actual complaint. "wah kya quality hai, ek din me phat gaya" is defect_quality.

Rules for the fields:
- fit_direction and fit_area must be null unless reason is "fit". fit_area is only for area_specific.
- secondary_reason: if the comment clearly gives a second reason ("size chhota aur colour bhi alag"), choose the one the customer stresses or mentions first as reason, and put the other reason's key (one of the seven above) in secondary_reason. Otherwise null.
- gist_en: one plain English sentence saying what the customer said, at most 120 characters. No names, phone numbers or emails. Do not add anything the customer did not say.
- confidence: how likely it is that a careful person reading the same comment would pick the same reason.
    0.9 or higher  one reason, stated plainly
    0.7 to 0.9     a clear main reason, with a second reason or a little ambiguity
    0.4 to 0.7     two reasons are about equally likely, or you had to guess what a word meant
    below 0.4      too vague to tell ("accha nahi laga", "theek nahi hai"), or no reason given
  Do not default to a high number. A low-confidence answer gets a second look; a confident wrong answer does not.
"""


def make_model(model_id: str, temperature: float) -> ChatOpenAI:
    """A LangChain chat model that talks to OpenRouter. Model IDs come from .env, never from code."""
    return ChatOpenAI(
        model=model_id,
        temperature=temperature,
        # Only the key is required here, so eval.py can run before the thresholds are decided.
        api_key=get_settings(("OPENROUTER_API_KEY",)).OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        timeout=30,
        max_retries=2,  # for timeouts and 5xx; after that the exception reaches the routing below
    )


def _to_result(out: dict) -> LLMResult[Any]:
    """Last step of the chain: turn the structured-output dict into an LLMResult, or raise."""
    # With include_raw=True a schema failure is returned, not raised. Raise it ourselves.
    if out.get("parsing_error") is not None:
        raise out["parsing_error"]
    if out.get("parsed") is None:
        raise ValueError("model did not return a structured answer")
    usage = getattr(out.get("raw"), "usage_metadata", None) or {}
    return LLMResult(out["parsed"], usage.get("input_tokens", 0), usage.get("output_tokens", 0))


def structured_call(
    model: BaseChatModel, schema: type[BaseModel], system_prompt: str
) -> Callable[[str], LLMResult[Any]]:
    """Build the chain and return a function of the human message text.

    The chain is three Runnables piped together (LCEL):

        prompt  |  model with structured output  |  _to_result
        (ChatPromptTemplate)  (ChatOpenAI + schema as a forced tool call)  (RunnableLambda)

    Shared with brief.py. The returned function raises on any failure
    (timeout, 5xx, no structured answer, output that does not fit the schema).
    """
    # SystemMessage, not a template string: the prompt is fixed text and must not be parsed for {variables}.
    prompt = ChatPromptTemplate.from_messages([SystemMessage(content=system_prompt), ("human", "{input}")])
    # function_calling (tool calling) is the structured-output method most OpenRouter
    # models support. include_raw keeps the raw message, which carries the token counts.
    structured = model.with_structured_output(schema, method="function_calling", include_raw=True)
    chain: Runnable[dict, LLMResult[Any]] = prompt | structured | RunnableLambda(_to_result)

    def call(text: str) -> LLMResult[Any]:
        return chain.invoke({"input": text})

    return call


def build_classifier(model_id: str) -> Classifier:
    """A classifier for one model (built once for Model A and once for Model B).

    Temperature 0: classification must be repeatable.
    The model must support tool calling on OpenRouter, or every call fails.
    """
    return structured_call(make_model(model_id, temperature=0.0), ReturnClassification, CLASSIFY_SYSTEM_PROMPT)


# ==========================================================================
# 2. ROUTING HALF — written
# ==========================================================================


@dataclass
class Attempt:
    """One model's try at one comment."""

    model: Literal["A", "B"]
    classification: Optional[ReturnClassification] = None
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def valid(self) -> bool:
        return self.classification is not None

    def accepted(self, threshold: float) -> bool:
        return self.classification is not None and self.classification.confidence >= threshold

    def why_rejected(self, threshold: float) -> str:
        if self.classification is None:
            return f"Model {self.model} failed: {self.error}"
        return (
            f"Model {self.model} was unsure "
            f"(confidence {self.classification.confidence:.2f}, needs {threshold:.2f})"
        )


@dataclass
class RoutedResult:
    status: Literal["classified", "unclassified"]
    classification: Optional[ReturnClassification]
    model_used: Literal["A", "B", "none"]
    routed: bool  # True when Model B was tried
    error: Optional[str] = None
    attempts: list[Attempt] = field(default_factory=list)


class ModelSetupError(RuntimeError):
    """The model step is missing or could not be built. The message is shown as is."""


def _short(exc: BaseException, limit: int = 240) -> str:
    if isinstance(exc, (ModelSetupError, NotImplementedError)) and str(exc):
        text = str(exc)
    elif isinstance(exc, ValidationError):
        text = "output did not match the schema: " + "; ".join(e["msg"] for e in exc.errors()[:3])
    else:
        text = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def attempt(model: Literal["A", "B"], classifier: Classifier, text: str) -> Attempt:
    """Call one classifier. Never raises: any failure becomes an invalid Attempt."""
    try:
        result = classifier(text)
        # Be forgiving about what the LangChain half hands back.
        if isinstance(result, LLMResult):
            parsed, tokens_in, tokens_out = result.parsed, result.input_tokens, result.output_tokens
        else:
            parsed, tokens_in, tokens_out = result, 0, 0
        if parsed is None:
            return Attempt(model, error="model returned nothing")
        classification = ReturnClassification.model_validate(
            parsed.model_dump() if isinstance(parsed, ReturnClassification) else parsed
        )
        return Attempt(model, classification, None, int(tokens_in or 0), int(tokens_out or 0))
    except Exception as exc:  # timeouts, 5xx, schema failures, NotImplementedError
        return Attempt(model, error=_short(exc))


def route(text: str, model_a: Classifier, model_b: Classifier, threshold: float) -> RoutedResult:
    """Model A; if its answer is invalid or below the threshold, Model B; else unclassified.

        result = try Model A
        if result is invalid schema OR result.confidence < CONFIDENCE_THRESHOLD:
            result = try Model B
            if result is invalid schema OR result.confidence < CONFIDENCE_THRESHOLD:
                status = "unclassified"
    """
    first = attempt("A", model_a, text)
    if first.accepted(threshold):
        return RoutedResult("classified", first.classification, "A", routed=False, attempts=[first])

    second = attempt("B", model_b, text)
    if second.accepted(threshold):
        return RoutedResult("classified", second.classification, "B", routed=True, attempts=[first, second])

    if first.error and first.error == second.error:
        error = f"Both models failed: {first.error}"
    else:
        error = f"{first.why_rejected(threshold)}. {second.why_rejected(threshold)}."
    return RoutedResult(
        "unclassified",
        None,
        "none",
        routed=True,
        error=error,
        attempts=[first, second],
    )


def safe_build(builder: Callable[..., Callable], *args) -> Callable:
    """Call a `build_*` function; if it fails, return a stand-in that fails per call.

    This keeps a broken model setup visible as "couldn't classify"
    rows (with the reason) instead of crashing the whole run.
    """
    try:
        return builder(*args)
    except Exception as exc:
        message = _short(exc)

        def unavailable(*_args, **_kwargs):
            raise ModelSetupError(message)

        return unavailable
