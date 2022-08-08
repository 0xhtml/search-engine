"""Module containing functions to work with queries."""

import re
from typing import NamedTuple

from .lang import detect_lang


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    query_parts: list[str]
    lang: str

    def to_string(self, simple: bool):
        """Convert query parts to (simple) query string."""
        if simple:
            return " ".join(self.query_parts)

        string = ""

        for query_part in self.query_parts:
            if " " in query_part:
                string += f'"{query_part}" '
            else:
                string += f"{query_part} "

        return string[:-1]


_REGEX_QUERY = re.compile(r"\"([^\"]+)\"?|:(:\S*)|:(\S+)|(\S+)")


def parse_query(query: str) -> ParsedQuery:
    """Parse a raw query into a parsed query."""
    query_parts = []
    lang = None

    for m in _REGEX_QUERY.finditer(query):
        if m[1]:
            query_parts.append(" ".join(m[1].split()))
        elif m[3]:
            lang = m[3]
        else:
            query_parts.append(m[2] or m[4])

    if lang is None:
        lang = detect_lang(" ".join(query_parts))

    return ParsedQuery(query_parts, lang)
