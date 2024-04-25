"""Module containing functions to work with queries."""

import re
from typing import NamedTuple

from .lang import detect_lang


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    query_parts: list[str]
    lang: str

    def to_string(self, simple: bool) -> str:
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


_REGEX_QUERY = re.compile(r"\"([^\"]*)\"?|:(\S+)|(\S+)")


def parse_query(query: str) -> ParsedQuery:
    """Parse a raw query into a parsed query."""
    query_parts = []
    lang = None

    for m in _REGEX_QUERY.finditer(query):
        if m[1] is not None:
            part = " ".join(m[1].split())
            if part:
                query_parts.append(part)
        elif m[2]:
            if m[2][0] == ":":
                query_parts.append(m[2])
            else:
                lang = m[2]
        else:
            query_parts.append(m[3])

    if lang is None:
        lang = detect_lang(" ".join(query_parts))

    return ParsedQuery(query_parts, lang)
