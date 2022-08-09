"""Custom (meta) search engine."""

import asyncio
import gettext

import httpx
from flask import Flask, make_response, render_template, request

from .engines import get_lang_engines
from .query import parse_query
from .results import order_results
from .template_filter import TEMPLATE_FILTER_MAP

_ = gettext.translation("msg", "locales", fallback=True).gettext

application = Flask(__name__)
application.jinja_env.filters.update(TEMPLATE_FILTER_MAP)
application.jinja_env.globals["_"] = _


def error(message: str):
    """Return error page."""
    return render_template(
        "index.html", title=_("Error"), error_message=message
    )


@application.errorhandler(404)
def page_not_found(code):
    """Return 404 error page."""
    if "text/html" in request.headers.get("Accept", ""):
        return error(_("The requested page was not not found")), 404

    response = make_response("404 Not Found", 404)
    response.headers["Content-Type"] = "text/plain"
    return response


@application.route("/")
def index():
    """Return the start page."""
    return render_template("index.html", title=_("Search"))


@application.route("/search")
def search():
    """Perform a search and return the search result page."""
    query = request.args.get("q", None, str)

    if query is None:
        return error(_("No search term was received")), 404

    query = query.strip()

    if not query:
        return error(_("The search term is empty"))

    parsed_query = parse_query(query)

    lang_engines = get_lang_engines(parsed_query.lang)

    async def async_results():
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=10),
            timeout=httpx.Timeout(5, pool=None),
        ) as client:
            return await asyncio.gather(
                *[
                    engine(client).search(parsed_query)
                    for engine in lang_engines
                ]
            )

    results = asyncio.run(async_results())
    results = order_results(results, parsed_query.lang)

    return render_template(
        "search.html",
        title=query,
        query=query,
        parsed_query=parsed_query,
        results=results,
    )


@application.route("/opensearch.xml")
def opensearch():
    """Return opensearch.xml."""
    response = make_response(render_template("opensearch.xml"))
    response.headers["Content-Type"] = "application/xml"
    return response
