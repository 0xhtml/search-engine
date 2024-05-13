"""Tests for the query parsing and string convertion."""

from typing import Optional

import pytest
from searchengine.query import QueryParser


@pytest.mark.parametrize(
    "query,words,lang",
    [
        ("This is a test!", ["This", "is", "a", "test!"], None),
        ('Th"s "is a" test!', ['Th"s', "is a", "test!"], None),
        ('This "is a test!', ["This", "is a test!"], None),
        (' This  "is   a"     test!  ', ["This", "is   a", "test!"], None),
        (':1 "is :2 a" :3 test!', ["is :2 a", "test!"], "3"),
        ('::1 "is :2 a":: test :', [":1", "is :2 a", ":", "test", ":"], None),
        ('""  "   " test', ["   ", "test"], None)
    ],
)
def test_parse_query(query: str, words: list[str], lang: Optional[str]):
    """Test the parse_query function."""
    parsed_query = QueryParser().parse_query(query)
    assert parsed_query.words == words
    if lang is not None:
        assert parsed_query.lang == lang
