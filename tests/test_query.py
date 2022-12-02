"""Tests for the query parsing and string convertion."""

from typing import Optional


def test_parse_query(benchmark):
    """Test the parse_query function."""
    from searchengine.query import parse_query

    def test(inp: str, parts: list[str], lang: Optional[str] = None) -> None:
        parsed_query = parse_query(inp)

        assert parsed_query.query_parts == parts

        if lang is not None:
            assert parsed_query.lang == lang

    test("This is a test!", ["This", "is", "a", "test!"])
    test('Th"s "is a" test!', ['Th"s', "is a", "test!"])
    test('This "is a test!', ["This", "is a test!"])
    test(' This  "is   a"     test!  ', ["This", "is a", "test!"])
    test(':1 "is :2 a" :3 test!', ["is :2 a", "test!"], "3")
    test('::1 "is :2 a":: test! :', [":1", "is :2 a", ":", "test!", ":"])
    test('""  "   " test', ["test"])

    benchmark(parse_query, '  Th"is" :de is ::    "  a test" ::right! :en  ')
