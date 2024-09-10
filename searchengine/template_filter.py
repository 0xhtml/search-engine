"""Module containing filter functions for the templates."""

from urllib.parse import unquote, urlencode

import markupsafe
from jinja2 import pass_context

from .query import ParsedQuery
from .sha import gen_sha
from .url import Url


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


def _pretty_url(url: Url) -> markupsafe.Markup:
    return markupsafe.escape(url._replace(path=unquote(url.path)))


@pass_context
def _proxy(ctx: dict, url: Url) -> str:
    return (
        str(ctx["request"].url_for("img"))
        + "?"
        + urlencode({"url": url, "sha": gen_sha(url)})
    )


TEMPLATE_FILTER_MAP = {
    "highlight": _highlight,
    "pretty_url": _pretty_url,
    "proxy": _proxy,
}
