"""Fake models for tests. No test calls the real OpenRouter API."""

from app.pipeline.classify import LLMResult
from app.schemas import ReturnClassification


def classification(reason="fit", confidence=0.9, **kw) -> ReturnClassification:
    if reason == "fit":
        kw.setdefault("fit_direction", "runs_small")
    return ReturnClassification(reason=reason, confidence=confidence, gist_en=kw.pop("gist_en", "gist"), **kw)


class FakeClassifier:
    """Returns (or raises) whatever it was given, and records what it was asked."""

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[str] = []

    def __call__(self, text: str):
        self.calls.append(text)
        answer = self.answer(text) if callable(self.answer) else self.answer
        if isinstance(answer, BaseException):
            raise answer
        return answer


def answers(reason="fit", confidence=0.9, tokens=(100, 20), **kw) -> FakeClassifier:
    return FakeClassifier(LLMResult(classification(reason, confidence, **kw), *tokens))
