"""Tests for the query parsing and string convertion."""

from typing import Optional

import pytest
from searchengine.query import parse_query


@pytest.mark.parametrize(
    ("query", "words", "lang", "site"),
    [
        ("This is a test!", ["This", "is", "a", "test!"], None, None),
        ('Th"s "is a" test!', ['Th"s', "is a", "test!"], None, None),
        ('This "is a test!', ["This", "is a test!"], None, None),
        (' This  "is   a"     test!  ', ["This", "is   a", "test!"], None, None),
        (':1 "is :2 a" :de test!', [":1", "is :2 a", "test!"], "de", None),
        ('::1 "is :2 a":: test :', ["::1", "is :2 a", "::", "test", ":"], None, None),
        ('""  "   " test', ['""', "   ", "test"], None, None),
        (": :: :::", [":", "::", ":::"], None, None),
        ("site:", ["site:"], None, None),
        ('":de" :en', [":de"], "en", None),
        ('"lang:de" lang:en', ["lang:de"], "en", None),
        ('"site:1" site:2', ["site:1"], None, "2"),
    ],
)
def test_parse_query(
    query: str, words: list[str], lang: Optional[str], site: Optional[str]
) -> None:
    """Test the parse_query function."""
    parsed_query = parse_query(query)
    assert parsed_query.words == words
    if lang is not None:
        assert parsed_query.lang == lang
    assert parsed_query.site == site
