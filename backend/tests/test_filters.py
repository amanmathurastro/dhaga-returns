import pytest

from app.pipeline.filters import junk_reason, scrub_pii


@pytest.mark.parametrize(
    "text, expected",
    [
        (None, "blank"),
        ("", "blank"),
        ("   \n", "blank"),
        ("ok", "filler"),
        ("OK.", "filler"),
        ("Nothing!!", "filler"),
        ("kuch nahi", "filler"),
        ("👍", "no_words"),
        ("😡😡😡", "no_words"),
        ("...", "no_words"),
        ("12345", "no_words"),
        ("xl", "too_short"),
    ],
)
def test_junk_is_caught(text, expected):
    assert junk_reason(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "size chhota hai",
        "bad",
        "Colour alag tha 😡",
        "छोटा",  # 2 letters + 2 vowel signs: must not be mistaken for too short
        "साइज़ बहुत छोटा है",
        "kurta L manga tha M jaisa fit",
    ],
)
def test_real_comments_are_kept(text):
    assert junk_reason(text) is None


def test_min_chars_is_configurable():
    assert junk_reason("bad", min_chars=3) is None
    assert junk_reason("bad", min_chars=4) == "too_short"


@pytest.mark.parametrize(
    "raw, scrubbed",
    [
        ("call me 9876543210 size chhota", "call me [phone] size chhota"),
        ("+91 98765 43210 pe call karo", "[phone] pe call karo"),
        ("+91-9876543210", "[phone]"),
        ("09876543210 wapas lo", "[phone] wapas lo"),
        ("mail neha.k+shop@gmail.com please", "mail [email] please"),
        ("9876543210 ya rk@yahoo.co.in", "[phone] ya [email]"),
    ],
)
def test_pii_is_scrubbed(raw, scrubbed):
    assert scrub_pii(raw) == scrubbed


@pytest.mark.parametrize(
    "text",
    [
        "size 38 manga tha 40 aaya",
        "order 12345 ka kurta",
        "2 din me colour nikal gaya",
        "paid 1299 for this",
        "ordered 15 08 2026",
    ],
)
def test_ordinary_numbers_are_left_alone(text):
    assert scrub_pii(text) == text


def test_scrub_handles_missing_text():
    assert scrub_pii(None) == ""


def test_comment_that_is_only_pii_is_junk():
    assert junk_reason(scrub_pii("9876543210")) == "no_words"
    assert junk_reason(scrub_pii("me@example.com")) == "no_words"
