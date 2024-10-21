"""Module containing functions to work with queries."""

from enum import Enum
from typing import NamedTuple, Optional

import ply.lex

from .lang import detect_lang, parse_accept_language


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
    lang: str
    site: Optional[str]

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

    def t_LANG(self, t: ply.lex.LexToken) -> ply.lex.LexToken:
        r"lang:\S+|:(de|en)(?!\S)"
        t.value = t.value.removeprefix("lang").removeprefix(":")
        return t

    def t_SITE(self, t: ply.lex.LexToken) -> ply.lex.LexToken:
        r"site:\S+"
        t.value = t.value.removeprefix("site:")
        return t

    def t_QUOTED_WORD(self, t: ply.lex.LexToken) -> ply.lex.LexToken:
        r'"[^"]+("|$)'
        t.value = t.value.strip('"')
        return t

    t_WORD = r"\S+"
    t_ignore = " "

    def t_error(self, t: ply.lex.LexToken) -> None:
        raise RuntimeError(f"Unexpected token: {t.value}")

    def __init__(self) -> None:
        """Initialize the query parser."""
        self.lexer = ply.lex.lex(module=self)

    def parse_query(self, query: str, accept_language: str) -> ParsedQuery:
        """Parse a search query into a (words, lang, site) tuple."""
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
            languages = parse_accept_language(accept_language)
            lang = detect_lang(" ".join(words), languages or ["en"])

        return ParsedQuery(words, lang, site)
