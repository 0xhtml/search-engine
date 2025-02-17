"""Module containing functions to work with queries."""

from typing import NamedTuple, Optional

import ply.lex


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    words: list[str]
    lang: Optional[str]
    site: Optional[str]


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

    def parse_query(self, query: str) -> ParsedQuery:
        """Parse a search query into a ParsedQuery."""
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

        return ParsedQuery(words, lang, site)
