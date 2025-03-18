"""Tests for the custom template filters."""

import pytest
from searchengine.query import ParsedQuery
from searchengine.templates import _highlight


@pytest.mark.parametrize(
    ("words", "before", "after"),
    [
        (["world"], "Hello World!", "Hello <b>World</b>!"),
        (["middle"], "inthemiddleofaword!", "inthe<b>middle</b>ofaword!"),
        (
            ["mult"],
            "a mult b mult c mult d",
            "a <b>mult</b> b <b>mult</b> c <b>mult</b> d",
        ),
        (["a", "abc"], "abcde", "<b>abc</b>de"),
        (["c", "abc"], "abcde", "<b>abc</b>de"),
        (["worda", "aword"], "wordaword", "<b>wordaword</b>"),
        (["back", "to"], "backtoback", "<b>backtoback</b>"),
        (["word", "longwordlong"], "longwordlong", "<b>longwordlong</b>"),
        (["abba"], "abbabba", "<b>abbabba</b>"),
        (["a", "b"], "bca", "<b>b</b>c<b>a</b>"),
        (["a"], "&a&", "&amp;<b>a</b>&amp;"),
    ],
)
def test_highlight(words: list[str], before: str, after: str) -> None:
    """Test highlighting of query parts."""
    query = ParsedQuery(words, "", None)
    assert _highlight(before, query) == after
