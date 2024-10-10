"""Tests for the custom template filters."""

import pytest
from searchengine.query import ParsedQuery, SearchMode
from searchengine.template_filter import _highlight


@pytest.mark.parametrize(
    ("query", "before", "after"),
    [
        (
            ParsedQuery(["world"], SearchMode.WEB, 1, "", None),
            "Hello World!",
            "Hello <b>World</b>!",
        ),
        (
            ParsedQuery(["middle"], SearchMode.WEB, 1, "", None),
            "inthemiddleofaword!",
            "inthe<b>middle</b>ofaword!",
        ),
        (
            ParsedQuery(["mult"], SearchMode.WEB, 1, "", None),
            "a mult b mult c mult d",
            "a <b>mult</b> b <b>mult</b> c <b>mult</b> d",
        ),
        (
            ParsedQuery(["a", "abc"], SearchMode.WEB, 1, "", None),
            "abcde",
            "<b>abc</b>de",
        ),
        (
            ParsedQuery(["c", "abc"], SearchMode.WEB, 1, "", None),
            "abcde",
            "<b>abc</b>de",
        ),
        (
            ParsedQuery(["worda", "aword"], SearchMode.WEB, 1, "", None),
            "wordaword",
            "<b>wordaword</b>",
        ),
        (
            ParsedQuery(["back", "to"], SearchMode.WEB, 1, "", None),
            "backtoback",
            "<b>backtoback</b>",
        ),
        (
            ParsedQuery(["word", "longwordlong"], SearchMode.WEB, 1, "", None),
            "longwordlong",
            "<b>longwordlong</b>",
        ),
        (
            ParsedQuery(["abba"], SearchMode.WEB, 1, "", None),
            "abbabba",
            "<b>abbabba</b>",
        ),
        (
            ParsedQuery(["a", "b"], SearchMode.WEB, 1, "", None),
            "bca",
            "<b>b</b>c<b>a</b>",
        ),
        (
            ParsedQuery(["a"], SearchMode.WEB, 1, "", None),
            "&a&",
            "&amp;<b>a</b>&amp;",
        ),
    ],
)
def test_highlight(query: ParsedQuery, before: str, after: str) -> None:
    """Test highlighting of query parts."""
    assert _highlight(before, query) == after
