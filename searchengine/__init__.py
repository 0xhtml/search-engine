"""Custom (meta) search engine."""

import asyncio
import gettext
import traceback

import curl_cffi
import jinja2
from curl_cffi.requests import AsyncSession
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .engines import Engine, SearchMode, get_engines
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


class _EngineError(Exception):
    def __init__(self, engine: Engine, exc: BaseException) -> None:
        self.engine = engine
        self.exc = exc

    def __str__(self) -> str:
        return f"{self.engine}: {traceback.format_exception_only(self.exc)[0]}"


async def _engine_search(
    engine: Engine, session: AsyncSession, query: ParsedQuery
) -> tuple[Engine, list[Result]]:
    try:
        return engine, await engine.search(session, query)
    except BaseException as e:
        if not isinstance(e, asyncio.CancelledError):
            traceback.print_exc()
        raise _EngineError(engine, e) from e


async def search(request: Request) -> Response:
    """Perform a search and return the search result page."""
    query = request.query_params.get("q")
    if query is None:
        return _error(request, _("No search term was received"), 404)

    query = query.strip()
    if not query:
        return _error(request, _("The search term is empty"))

    mode = SearchMode(request.query_params.get("mode", SearchMode.WEB))

    try:
        page = int(request.query_params["page"])
    except (ValueError, KeyError):
        page = 1

    parsed_query = _QUERY_PARSER.parse_query(query, mode, page)

    engines = get_engines(parsed_query)
    important_engines = {engine for engine in engines if engine.weight > 1}

    errors = []
    results = []

    async with AsyncSession(impersonate="chrome") as session:
        tasks = {
            asyncio.create_task(_engine_search(engine, session, parsed_query))
            for engine in engines
        }

        while tasks:
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    results.append(task.result())
                except _EngineError as e:
                    errors.append(e)
            if (
                {e for e, _ in results} | {e.engine for e in errors}
            ) >= important_engines:
                break

        await asyncio.wait(tasks, timeout=0.5)

        for task in tasks:
            task.cancel()
            try:
                results.append(await task)
            except _EngineError as e:
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
            "results": rated_results,
            "engine_errors": errors,
        },
    )


async def img(request: Request) -> Response:
    """Proxy an image."""
    url = request.query_params.get("url", None)
    if url is None:
        return _error(request, "Not Found", 404)

    sha = request.query_params.get("sha", None)
    if sha is None or gen_sha(url) != sha:
        return _error(request, "Unauthorized", 401)

    async with AsyncSession(impersonate="chrome") as session:
        try:
            resp = await session.get(url, headers={"Accept": "image/*"})
        except curl_cffi.CurlError as e:
            return _error(request, str(e), 500)

    if not (200 <= resp.status_code < 300):
        return _error(request, f"{resp.status_code} {resp.reason}", resp.status_code)

    if not resp.headers.get("Content-Type", "").startswith("image/"):
        return _error(request, "Not an image", 500)

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
