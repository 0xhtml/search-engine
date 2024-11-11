"""Module containing filter functions for the templates."""

import traceback
from typing import Any
from urllib.parse import unquote, urlencode

import markupsafe
from jinja2 import pass_context

from .query import ParsedQuery
from .sha import gen_sha
from .url import Url


def _highlight(string: str, query: ParsedQuery) -> markupsafe.Markup:
    higlights: list[tuple[int, int]] = []
    for word in query.words:
        pos = 0
        while (pos := string.lower().find(word.lower(), pos)) >= 0:
            start = pos
            end = pos + len(word)

            for s, e in higlights:
                if s <= start <= e:
                    start = s
                if s <= end <= e:
                    end = e

            higlights = [(s, e) for s, e in higlights if e < start or s > end]
            higlights.append((start, end))

            pos += 1

    pend = 0
    result = markupsafe.Markup("")
    for start, end in sorted(higlights):
        result += (
            markupsafe.escape(string[pend:start])
            + markupsafe.Markup("<b>")
            + markupsafe.escape(string[start:end])
            + markupsafe.Markup("</b>")
        )
        pend = end
    result += markupsafe.escape(string[pend:])

    return result


def _pretty_url(url: Url) -> markupsafe.Markup:
    return markupsafe.escape(url._replace(path=unquote(url.path)))


@pass_context
def _proxy(ctx: dict[str, Any], url: Url) -> str:
    return (
        str(ctx["request"].url_for("img"))
        + "?"
        + urlencode({"url": url, "sha": gen_sha(str(url))})
    )


def _pretty_exc(exc: Exception) -> str:
    return traceback.format_exception_only(exc)[0]


TEMPLATE_FILTER_MAP = {
    "highlight": _highlight,
    "pretty_url": _pretty_url,
    "proxy": _proxy,
    "pretty_exc": _pretty_exc,
}
