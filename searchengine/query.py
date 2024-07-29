"""Module containing functions to work with queries."""

from enum import Flag, auto
from typing import NamedTuple, Optional

import ply.lex

from .lang import detect_lang


class QueryExtensions(Flag):
    """Special query extensions that can be used."""

    QUOTES = auto()
    SITE = auto()


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    words: list[str]
    lang: str
    site: Optional[str]

    def required_extensions(self) -> QueryExtensions:
        """Determine which extensions are required for this query."""
        extensions = QueryExtensions(0)

        if any(" " in word for word in self.words):
            extensions |= QueryExtensions.QUOTES

        if self.site is not None:
            extensions |= QueryExtensions.SITE

        return extensions

    def __str__(self) -> str:
        """Convert query parts to query string."""
        query = ""

        for word in self.words:
            if " " in word:
                query += f'"{word}" '
            else:
                query += f"{word} "

        if self.site is not None:
            query += f"site:{self.site} "

        return query[:-1]


class QueryParser:
    """Parser for search queries."""

    tokens = ("LANG", "SITE", "WORD")

    def t_LANG(self, t):
        r":\S*"
        if t.value == ":":
            t.type = "WORD"
            return t
        t.value = t.value.removeprefix(":")
        if t.value:
            if t.value[0] == ":":
                t.type = "WORD"
            return t

    def t_SITE(self, t):
        r"site:\S*"
        t.value = t.value.removeprefix("site:")
        if t.value:
            return t

    def t_WORD(self, t):
        r'"[^"]*("|$)|\S+'
        t.value = t.value.strip('"')
        if t.value:
            return t

    t_ignore = " "

    def t_error(self, t):
        raise RuntimeError(f"Unexpected token: {t.value}")

    def __init__(self) -> None:
        """Initialize the query parser."""
        self.lexer = ply.lex.lex(module=self)

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse a search query into a ParsedQuery object."""
        self.lexer.input(query)

        words = []
        lang = None
        site = None

        while token := self.lexer.token():
            if token.type == "LANG":
                lang = token.value
            elif token.type == "SITE":
                site = token.value
            elif token.type == "WORD":
                words.append(token.value)

        if lang is None:
            lang = detect_lang(" ".join(words))

        return ParsedQuery(words, lang, site)
