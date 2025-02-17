"""Tests for the language handling functions."""

import pytest
from searchengine.lang import detect_lang, is_lang, parse_accept_language

_LANGUAGE_TEST_CASES = [
    ("this is english", "en"),
    ("dies ist deutsch", "de"),
    ("这是中文", "zh"),
    ("test", "en"),
]
_LANGUAGES = {lang for query, lang in _LANGUAGE_TEST_CASES}


@pytest.mark.parametrize(
    ("query", "languages", "expected"),
    [
        (
            query,
            ["unk", *(lang for lang in _LANGUAGES if lang != expected), expected],
            expected,
        )
        for query, expected in _LANGUAGE_TEST_CASES
    ]
    + [(query, ["unk"], "unk") for query, expected in _LANGUAGE_TEST_CASES],
)
def test_detect_lang(query: str, languages: list[str], expected: str) -> None:
    """Test the detect_lang function."""
    assert detect_lang(query, languages) == expected


@pytest.mark.parametrize(("query", "expected"), _LANGUAGE_TEST_CASES)
def test_is_lang(query: str, expected: str) -> None:
    """Test the is_lang function."""
    assert is_lang(query, expected) > 0.2
    for lang in _LANGUAGES:
        if lang != expected:
            assert is_lang(query, lang) < 0.02


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Test case from RFC 9110
        ("da, en-gb;q=0.8, en;q=0.7", ["da", "en"]),
        # Test cases from https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
        ("en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7", ["en", "zh"]),
        ("fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5", ["fr", "en", "de"]),
        ("de", ["de"]),
        ("de-CH", ["de"]),
        ("en-US,en;q=0.5", ["en"]),
    ],
)
def test_parse_accept_language(value: str, expected: list[str]) -> None:
    """Test the parse_accept_language function."""
    assert parse_accept_language(value) == expected
