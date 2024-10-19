"""Tests for the language handling functions."""

import pytest
from searchengine.lang import parse_accept_language


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
