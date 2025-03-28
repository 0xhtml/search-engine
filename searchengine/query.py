"""Module containing functions to work with queries."""

from typing import NamedTuple, Optional

import ply.lex


class ParsedQuery(NamedTuple):
    """Query parsed into actual query and extra data."""

    words: tuple[str, ...]
    lang: Optional[str]
    site: Optional[str]


tokens = ("LANG", "SITE", "QUOTED_WORD", "WORD")


def t_LANG(t: ply.lex.LexToken) -> ply.lex.LexToken:
    r"lang:\S+|:(de|en)(?!\S)"
    t.value = t.value.removeprefix("lang").removeprefix(":")
    return t


def t_SITE(t: ply.lex.LexToken) -> ply.lex.LexToken:
    r"site:\S+"
    t.value = t.value.removeprefix("site:")
    return t


def t_QUOTED_WORD(t: ply.lex.LexToken) -> ply.lex.LexToken:
    r'"[^"]+("|$)'
    t.value = t.value.strip('"')
    return t


t_WORD = r"\S+"
t_ignore = " "


def t_error(t: ply.lex.LexToken) -> None:
    raise RuntimeError(f"Unexpected token: {t.value}")


_LEXER = ply.lex.lex()


def parse_query(query: str) -> ParsedQuery:
    """Parse a search query into a ParsedQuery."""
    _LEXER.input(query)

    words: tuple[str, ...] = ()
    lang = None
    site = None

    while token := _LEXER.token():
        if token.type == "LANG":
            lang = token.value
        elif token.type == "SITE":
            site = token.value
        else:
            words += (token.value,)

    return ParsedQuery(words, lang, site)
