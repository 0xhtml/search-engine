"""Module containing functions to work with queries."""

from enum import Enum, Flag, auto
from typing import NamedTuple, Optional

import ply.lex

from .lang import detect_lang


class QueryExtensions(Flag):
    """Special query extensions that can be used."""

    PAGING = auto()
    QUOTES = auto()
    SITE = auto()


class SearchMode(Enum):
    """Search mode determining which type of results to return."""

    WEB = "web"
    IMAGES = "images"
    SCHOLAR = "scholar"

    def searx_category(self) -> str:
        """Convert search mode to searx category."""
        if self == SearchMode.WEB:
            return "general"
        if self == SearchMode.IMAGES:
            return "images"
        if self == SearchMode.SCHOLAR:
            return "science"
        raise ValueError


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    words: list[str]
    mode: SearchMode
    page: int
    lang: str
    site: Optional[str]

    def required_extensions(self) -> QueryExtensions:
        """Determine which extensions are required for this query."""
        extensions = QueryExtensions(0)

        if self.page != 1:
            extensions |= QueryExtensions.PAGING

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

    tokens = ("LANG", "SITE", "QUOTED_WORD", "WORD")

    def t_LANG(self, t):
        r"lang:\S+|:(de|en)(?!\S)"
        t.value = t.value.removeprefix("lang").removeprefix(":")
        return t

    def t_SITE(self, t):
        r"site:\S+"
        t.value = t.value.removeprefix("site:")
        return t

    def t_QUOTED_WORD(self, t):
        r'"[^"]+("|$)'
        t.value = t.value.strip('"')
        return t

    t_WORD = r"\S+"
    t_ignore = " "

    def t_error(self, t):
        raise RuntimeError(f"Unexpected token: {t.value}")

    def __init__(self) -> None:
        """Initialize the query parser."""
        self.lexer = ply.lex.lex(module=self)

    def parse_query(self, query: str, mode: SearchMode, page: int) -> ParsedQuery:
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
            else:
                words.append(token.value)

        if lang is None:
            lang = detect_lang(" ".join(words))

        return ParsedQuery(words, mode, page, lang, site)
