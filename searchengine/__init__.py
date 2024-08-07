"""Custom (meta) search engine."""

import asyncio
import gettext

import httpx
import jinja2
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .engines import Engine, EngineError, SearchMode, get_engines
from .query import ParsedQuery, QueryParser
from .rate import MAX_RESULTS, rate_results
from .results import Result
from .sha import gen_sha
from .template_filter import TEMPLATE_FILTER_MAP

_ = gettext.translation("msg", "locales", fallback=True).gettext

_ENV = jinja2.Environment(
    autoescape=True,
    loader=jinja2.FileSystemLoader("templates"),
    lstrip_blocks=True,
    trim_blocks=True,
)
_ENV.globals["_"] = _
_ENV.globals["SearchMode"] = SearchMode
_ENV.filters.update(TEMPLATE_FILTER_MAP)

_TEMPLATES = Jinja2Templates(env=_ENV)

_QUERY_PARSER = QueryParser()


def _error(request: Request, message: str, status_code: int = 200) -> Response:
    if "text/html" in request.headers.get("Accept", ""):
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {"title": _("Error"), "error_message": message},
            status_code,
        )
    return Response(message, status_code, media_type="text/plain")


def page_not_found(request: Request, exception: Exception) -> Response:
    """Return 404 error page."""
    return _error(request, _("The requested page was not not found"), 404)


def index(request: Request) -> HTMLResponse:
    """Return the start page."""
    return _TEMPLATES.TemplateResponse(request, "index.html", {"title": _("Search")})


async def _engine_search(
    engine: type[Engine], client: httpx.AsyncClient, query: ParsedQuery
) -> tuple[type[Engine], list[Result]]:
    return engine, await engine.search(client, query)


async def search(request: Request) -> Response:
    """Perform a search and return the search result page."""
    query = request.query_params.get("q")
    if query is None:
        return _error(request, _("No search term was received"), 404)

    query = query.strip()
    if not query:
        return _error(request, _("The search term is empty"))

    parsed_query = _QUERY_PARSER.parse_query(query)
    mode = SearchMode(request.query_params.get("mode", SearchMode.WEB))
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

    rated_results = list(rate_results(results, parsed_query.lang))
    rated_results.sort(reverse=True)
    del rated_results[MAX_RESULTS:]

    return _TEMPLATES.TemplateResponse(
        request,
        "search.html",
        {
            "title": query,
            "query": query,
            "parsed_query": parsed_query,
            "mode": mode,
            "results": rated_results,
            "engine_errors": errors,
        },
    )


def img(request: Request) -> Response:
    """Proxy an image."""
    url = request.query_params.get("url", None)
    if url is None:
        return _error(request, "Not Found", 404)

    sha = request.query_params.get("sha", None)
    if sha is None or gen_sha(httpx.URL(url)) != sha:
        return _error(request, "Unauthorized", 401)

    try:
        resp = httpx.get(url)
        resp.raise_for_status()
        if not resp.headers.get("Content-Type", "").startswith("image/"):
            raise httpx.HTTPError("Not an image")
    except httpx.HTTPError as e:
        return _error(request, str(e), 500)

    return Response(
        content=resp.content, media_type=resp.headers["Content-Type"]
    )


def opensearch(request: Request) -> HTMLResponse:
    """Return opensearch.xml."""
    return _TEMPLATES.TemplateResponse(
        request, "opensearch.xml", media_type="application/xml"
    )


app = Starlette(
    routes=[
        Route("/", endpoint=index),
        Route("/search", endpoint=search),
        Route("/img", endpoint=img),
        Route("/opensearch.xml", endpoint=opensearch),
        Mount("/static", app=StaticFiles(directory="static"), name="static"),
    ],
    exception_handlers={404: page_not_found},
)
