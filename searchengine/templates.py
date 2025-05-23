"""Module containing filter functions for the templates."""

from typing import Any
from urllib.parse import unquote, urlencode

import idna
import jinja2
import markupsafe
from starlette.templating import Jinja2Templates

from .common import SearchMode, pretty_exc
from .engines import ENGINES, EngineFeatures
from .query import ParsedQuery
from .sha import gen_sha
from .url import URL


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


def _pretty_url(url: URL) -> markupsafe.Markup:
    return markupsafe.escape(
        url._replace(
            host=idna.decode(url.host),
            path=unquote(url.path),
            query=unquote(url.query) if url.query is not None else None,
        ).geturl()
    )


@jinja2.pass_context
def _proxy(ctx: dict[str, Any], url: URL) -> str:
    return (
        str(ctx["request"].url_for("img"))
        + "?"
        + urlencode({"url": url.geturl(), "sha": gen_sha(url.geturl())})
    )


def _checkmark(value: bool) -> str:
    return "✅" if value else "❌"


_ENV = jinja2.Environment(
    autoescape=True,
    loader=jinja2.FileSystemLoader("templates"),
    lstrip_blocks=True,
    trim_blocks=True,
    extensions=["jinja2.ext.i18n"],
)
_ENV.globals["SearchMode"] = SearchMode
_ENV.globals["EngineFeatures"] = EngineFeatures
_ENV.globals["ENGINES"] = ENGINES
_ENV.filters.update(
    {
        "highlight": _highlight,
        "pretty_url": _pretty_url,
        "proxy": _proxy,
        "pretty_exc": pretty_exc,
        "checkmark": _checkmark,
    },
)

TEMPLATES = Jinja2Templates(env=_ENV)
