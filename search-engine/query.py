"""Module containing functions to work with queries."""

from typing import NamedTuple

from . import lang


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    query: str
    lang: str


def parse_query(query: str) -> ParsedQuery:
    """Parse a raw query into a parsed query."""
    parsed_query = []
    query_lang = None

    for query_part in query.split(" "):
        if query_part[0] == ":" and len(query_part) > 1:
            if query_part[1] == ":":
                parsed_query.append(query_part[1:])
            else:
                query_lang = query_part[1:]
        else:
            parsed_query.append(query_part)

    parsed_query = " ".join(parsed_query)

    if query_lang is None:
        query_lang = lang.detect_lang(parsed_query)

    return ParsedQuery(parsed_query, query_lang)
