"""Tests for the query parsing and string convertion."""

import pytest
from searchengine.query import ParsedQuery, parse_query


@pytest.mark.parametrize(
    ("query", "parsed_query"),
    [
        (
            "This is a test!",
            ParsedQuery(("This", "is", "a", "test!"), None, None),
        ),
        (
            'Th"s "is a" test!',
            ParsedQuery(('Th"s', "is a", "test!"), None, None),
        ),
        (
            'This "is a test!',
            ParsedQuery(("This", "is a test!"), None, None),
        ),
        (
            ' This  "is   a"     test!  ',
            ParsedQuery(("This", "is   a", "test!"), None, None),
        ),
        (
            ':1 "is :2 a" :de test!',
            ParsedQuery((":1", "is :2 a", "test!"), "de", None),
        ),
        (
            '::1 "is :2 a":: test :',
            ParsedQuery(("::1", "is :2 a", "::", "test", ":"), None, None),
        ),
        (
            '""  "   " test',
            ParsedQuery(('""', "   ", "test"), None, None),
        ),
        (
            ": :: :::",
            ParsedQuery((":", "::", ":::"), None, None),
        ),
        (
            "site:",
            ParsedQuery(("site:",), None, None),
        ),
        (
            '":de" :en',
            ParsedQuery((":de",), "en", None),
        ),
        (
            '"lang:de" lang:en',
            ParsedQuery(("lang:de",), "en", None),
        ),
        (
            '"site:1" site:2',
            ParsedQuery(("site:1",), None, "2"),
        ),
    ],
)
def test_parse_query(query: str, parsed_query: ParsedQuery) -> None:
    """Test the parse_query function."""
    assert parse_query(query) == parsed_query
