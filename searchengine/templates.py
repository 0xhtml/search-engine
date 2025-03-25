"""Module containing filter functions for the templates."""

import traceback
from typing import Any
from urllib.parse import ParseResult, unquote, urlencode

import idna
import jinja2
import markupsafe
from starlette.templating import Jinja2Templates

from .common import SearchMode
from .engines import ENGINES, EngineFeatures
from .query import ParsedQuery
from .sha import gen_sha


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


def _pretty_url(url: ParseResult) -> markupsafe.Markup:
    return markupsafe.escape(
        url._replace(
            netloc=idna.decode(url.netloc),
            path=unquote(url.path),
        ).geturl()
    )


@jinja2.pass_context
def _proxy(ctx: dict[str, Any], url: ParseResult) -> str:
    return (
        str(ctx["request"].url_for("img"))
        + "?"
        + urlencode({"url": url.geturl(), "sha": gen_sha(url.geturl())})
    )


def _pretty_exc(exc: BaseException) -> str:
    return traceback.format_exception_only(exc)[0]


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
        "pretty_exc": _pretty_exc,
        "checkmark": _checkmark,
    }
)

TEMPLATES = Jinja2Templates(env=_ENV)
