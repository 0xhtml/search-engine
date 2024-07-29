"""Module containing filter functions for the templates."""

import httpx
import markupsafe
from flask import url_for

from .query import ParsedQuery
from .sha import gen_sha


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    string = markupsafe.escape(string)

    for word in sorted(query.words, key=len, reverse=True):
        word_length = len(word)

        start = 0

        while (start := string.lower().find(word.lower(), start)) > -1:
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
    return markupsafe.escape(
        "".join(
            [
                url.scheme,
                "://",
                url.host,
                f":{url.port}" if url.port is not None else "",
                url.path,
                f"?{url.params}" if url.query else "",
                f"#{url.fragment}" if url.fragment else "",
            ],
        ),
    )


def _proxy(url: httpx.URL) -> str:
    return url_for("img", url=url, sha=gen_sha(url))


TEMPLATE_FILTER_MAP = {
    "highlight": _highlight,
    "pretty_url": _pretty_url,
    "proxy": _proxy,
}
