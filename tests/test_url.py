"""Tests for the URL class."""

import pytest
from searchengine.url import URL

_URLS_EQUAL_AFTER_NORMALIZATION = [
    ("http://example.com/foo%2a", "http://example.com/foo%2A"),
    ("HTTP://Example.COM/Foo", "http://example.com/Foo"),
    ("http://example.com/%7Efoo", "http://example.com/~foo"),
    ("http://example.com/./foo/bar/../baz", "http://example.com/foo/baz"),
    ("http://example.com:80/", "http://example.com/"),
]
_URLS_EQUAL_BY_COMPARISON = [
    ("http://example.com", "http://example.com/"),
    ("http://example.com/foo", "http://example.com/foo/"),
    ("http://example.com/bar.html#section1", "http://example.com/bar.html"),
    ("https://example.com/", "http://example.com/"),
    ("http://example.com/foo//bar.html", "http://example.com/foo/bar.html"),
    ("http://www.example.com/", "http://example.com/"),
    (
        "http://example.com/display?lang=en&article=fred",
        "http://example.com/display?article=fred&lang=en",
    ),
    ("http://example.com/display?", "http://example.com/display"),
    ("http://en.m.wikipedia.org/", "http://en.wikipedia.org/"),
    ("http://www.example.com/", "http://example.com/"),
    ("http://en.wikipedia.org/A%E2%80%93B", "http://en.wikipedia.org/A-B"),
]
_URLS_UNEQUAL = [
    ("ftp://example.com/", "http://example.com/"),
    ("http://foo.com/", "http://bar.com/"),
    ("http://example.com/foo", "http://example.com/bar"),
    ("http://example.com/?foo", "http://example.com/?bar"),
]


@pytest.mark.parametrize(
    ("a", "b", "is_equal"),
    [(a, b, True) for a, b in _URLS_EQUAL_AFTER_NORMALIZATION]
    + [(a, b, False) for a, b in _URLS_EQUAL_BY_COMPARISON]
    + [(a, b, False) for a, b in _URLS_UNEQUAL],
)
def test_url_parse_normalization(a: str, b: str, is_equal: bool) -> None:
    """Test the normalization of URL.parse."""
    assert a != b
    parsed_a = tuple(URL.parse(a))
    parsed_b = tuple(URL.parse(b))
    if is_equal:
        assert parsed_a == parsed_b
    else:
        assert parsed_a != parsed_b


@pytest.mark.parametrize(
    "url",
    [b for a, b in _URLS_EQUAL_AFTER_NORMALIZATION + _URLS_EQUAL_BY_COMPARISON]
    + [a for a, b in _URLS_EQUAL_BY_COMPARISON],
)
def test_url_geturl(url: str) -> None:
    """Test that URL.parse(url).geturl() == url."""
    assert URL.parse(url).geturl() == url


@pytest.mark.parametrize(
    ("a", "b", "is_equal"),
    [(a, b, True) for a, b in _URLS_EQUAL_AFTER_NORMALIZATION]
    + [(a, b, True) for a, b in _URLS_EQUAL_BY_COMPARISON]
    + [(a, b, False) for a, b in _URLS_UNEQUAL],
)
def test_url_eq(a: str, b: str, is_equal: bool) -> None:
    """Test __eq__ method of URL."""
    assert a != b
    parsed_a = URL.parse(a)
    parsed_b = URL.parse(b)
    if is_equal:
        assert parsed_a == parsed_b
        assert parsed_b == parsed_a
    else:
        assert not (parsed_a == parsed_b)
        assert not (parsed_b == parsed_a)
