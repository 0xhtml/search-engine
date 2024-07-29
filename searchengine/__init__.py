"""Custom (meta) search engine."""

import asyncio
import gettext

import httpx
from flask import Flask, make_response, render_template, request

from .engines import Engine, EngineError, SearchMode, get_engines
from .query import ParsedQuery, QueryParser
from .rate import MAX_RESULTS, rate_results
from .results import Result
from .sha import gen_sha
from .template_filter import TEMPLATE_FILTER_MAP

_ = gettext.translation("msg", "locales", fallback=True).gettext
_QUERY_PARSER = QueryParser()

application = Flask(__name__)
application.jinja_env.filters.update(TEMPLATE_FILTER_MAP)
application.jinja_env.globals["_"] = _
application.jinja_env.globals["SearchMode"] = SearchMode


def error(message: str, code: int = 200):
    """Return error page."""
    if "text/html" in request.headers.get("Accept", ""):
        return render_template("index.html", title=_("Error"), error_message=message), code

    response = make_response(message, code)
    response.headers["Content-Type"] = "text/plain"
    return response


@application.errorhandler(404)
def page_not_found(code):
    """Return 404 error page."""
    return error(_("The requested page was not not found"), 404)


@application.route("/")
def index():
    """Return the start page."""
    return render_template("index.html", title=_("Search"))


async def _engine_search(
    engine: type[Engine], client: httpx.AsyncClient, query: ParsedQuery
) -> tuple[type[Engine], list[Result]]:
    return engine, await engine.search(client, query)


@application.route("/search")
async def search():
    """Perform a search and return the search result page."""
    query = request.args.get("q", None, str)
    if query is None:
        return error(_("No search term was received"), 404)

    query = query.strip()
    if not query:
        return error(_("The search term is empty"))

    parsed_query = _QUERY_PARSER.parse_query(query)
    mode = request.args.get("mode", SearchMode.WEB, SearchMode)
    engines = get_engines(mode, parsed_query)

    errors = []
    results = []

    async with httpx.AsyncClient(
        limits=httpx.Limits(max_connections=10),
        timeout=httpx.Timeout(5, pool=None),
    ) as client:
        for coro in asyncio.as_completed(
            _engine_search(engine, client, parsed_query) for engine in engines
        ):
            try:
                results.append(await coro)
            except EngineError as e:
                e.engine._log(str(e))
                errors.append(e)

    results = list(rate_results(results, parsed_query.lang))
    results.sort(reverse=True)
    del results[MAX_RESULTS:]

    return render_template(
        "search.html",
        title=query,
        query=query,
        parsed_query=parsed_query,
        mode=mode,
        results=results,
        engine_errors=errors,
    )


@application.route("/img")
def img():
    """Proxy an image."""
    url = request.args.get("url", None, str)
    if url is None:
        return error("Not Found", 404)

    sha = request.args.get("sha", None, str)
    if sha is None or gen_sha(url) != sha:
        return error("Unauthorized", 401)

    try:
        httpx_resp = httpx.get(url)
        if not httpx_resp.is_success:
            raise httpx.HTTPError("Request failed")
        if not httpx_resp.headers.get("Content-Type", "").startswith("image/"):
            raise httpx.HTTPError("Not an image")
    except httpx.HTTPError as e:
        return error(str(e), 500)

    response = make_response(httpx_resp.content)
    response.headers["Content-Type"] = httpx_resp.headers["Content-Type"]
    return response


@application.route("/opensearch.xml")
def opensearch():
    """Return opensearch.xml."""
    response = make_response(render_template("opensearch.xml"))
    response.headers["Content-Type"] = "application/xml"
    return response
