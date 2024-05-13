"""Module containing filter functions for the templates."""

import httpx
import markupsafe

from .query import ParsedQuery


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    string = markupsafe.escape(string)

    for word in query.words:
        word = word.lower()
        word_length = len(word)

        start = 0

        while (start := string.lower().find(word, start)) > -1:
            bold = (
                markupsafe.Markup("<b>")
                + string[start : start + word_length]
                + markupsafe.Markup("</b>")
            )
            string = string[:start] + bold + string[start + word_length :]
            start += len(bold)

    return string


def _pretty_url(url: httpx.URL) -> markupsafe.Markup:
    assert url.is_absolute_url
    return markupsafe.escape("".join([
        url.scheme,
        "://",
        url.host,
        f":{url.port}" if url.port is not None else "",
        url.path,
        f"?{url.params}" if url.query else "",
        f"#{url.fragment}" if url.fragment else "",
    ]))


TEMPLATE_FILTER_MAP = {"highlight": _highlight, "pretty_url": _pretty_url}
