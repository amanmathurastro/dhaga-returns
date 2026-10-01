"""Junk filter and PII scrub. Plain code: no model sees a comment before this runs."""

import re
import unicodedata
from typing import Optional

PHONE_TOKEN = "[phone]"
EMAIL_TOKEN = "[email]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Indian mobile numbers: optional +91 / 91 / 0, then 10 digits starting 6-9,
# optionally split 5-5 by a space or dash.
_PHONE = re.compile(r"(?<![\d\w])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")

# Comments that say nothing. Compared after lowercasing and stripping punctuation.
_FILLER = {
    "ok", "okay", "k", "kk", "nothing", "none", "no", "na", "nil", "nope", "other", "others",
    "no reason", "no comment", "no comments", "nahi", "nahin", "kuch nahi", "kuch nahin",
    "test", "testing", "asdf", "return", "refund", "yes", "hmm", "idk",
}


def scrub_pii(text: Optional[str]) -> str:
    """Replace emails and phone numbers. Must run before text leaves our server."""
    if not text:
        return ""
    text = _EMAIL.sub(EMAIL_TOKEN, text)
    return _PHONE.sub(PHONE_TOKEN, text)


def _is_word_char(ch: str) -> bool:
    # Letters, digits, and combining marks (Devanagari vowel signs are marks, not letters).
    return unicodedata.category(ch)[0] in ("L", "M", "N")


def junk_reason(text: Optional[str], min_chars: int = 3) -> Optional[str]:
    """Why this comment is junk, or None if it is worth sending to a model.

    Pass text that has already been through `scrub_pii`: a comment that is only
    a phone number is junk.
    """
    if text is None or not text.strip():
        return "blank"
    cleaned = text.replace(PHONE_TOKEN, " ").replace(EMAIL_TOKEN, " ").strip()
    if not any(unicodedata.category(ch).startswith("L") for ch in cleaned):
        return "no_words"  # emoji, punctuation or digits only
    words = "".join(ch if _is_word_char(ch) else " " for ch in cleaned.lower()).split()
    if " ".join(words) in _FILLER:
        return "filler"
    if sum(len(w) for w in words) < min_chars:
        return "too_short"
    return None


JUNK_REASON_LABELS = {
    "blank": "Blank comment",
    "no_words": "No words (emoji, punctuation or numbers only)",
    "filler": "Filler text such as \"ok\" or \"nothing\"",
    "too_short": "Too short to mean anything",
}
