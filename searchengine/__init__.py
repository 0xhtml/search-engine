"""Custom (meta) search engine."""

import asyncio
import contextlib
import contextvars
import gettext
from typing import TYPE_CHECKING, AsyncIterator, TypedDict

import aiocache
import curl_cffi
import jinja2
from curl_cffi.requests import AsyncSession
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .engines import Engine, get_engines
from .query import ParsedQuery, QueryParser, SearchMode
from .rate import MAX_RESULTS, rate_results
from .results import Result
from .sha import gen_sha
from .template_filter import TEMPLATE_FILTER_MAP
from .utils import timed, timed_wait

_TRANSLATION = gettext.translation("messages", "locales", fallback=True)
_TRANSLATION.install()
if TYPE_CHECKING:
    _ = _TRANSLATION.gettext

_ENV = jinja2.Environment(
    autoescape=True,
    loader=jinja2.FileSystemLoader("templates"),
    lstrip_blocks=True,
    trim_blocks=True,
    extensions=["jinja2.ext.i18n"],
)
_ENV.install_gettext_translations(_TRANSLATION)  # type: ignore[attr-defined]
_ENV.globals["SearchMode"] = SearchMode
_ENV.filters.update(TEMPLATE_FILTER_MAP)

_TEMPLATES = Jinja2Templates(env=_ENV)

_QUERY_PARSER = QueryParser()

_MAX_AGE = 60 * 60

_CTX_ENGINE = contextvars.ContextVar("engine")


class _State(TypedDict):
    session: AsyncSession


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[_State]:
    async with AsyncSession(impersonate="chrome") as session:
        yield {"session": session}


def http_exception(request: Request, exc: HTTPException) -> Response:
    """Handle HTTP exceptions."""
    if "HX-Request" in request.headers:
        return _TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {
                "base": "htmx.html",
                "title": _("Error"),
                "error_message": exc.detail,
            },
            headers={"HX-Retarget": "#target", "HX-Reswap": "outerHTML"},
        )
    if "text/html" in request.headers.get("Accept", ""):
        return _TEMPLATES.TemplateResponse(
            request,
            "error.html",
            {
                "base": "base.html",
                "title": _("Error"),
                "error_message": exc.detail,
            },
            exc.status_code,
        )
    return Response(exc.detail, exc.status_code, media_type="text/plain")


def index(request: Request) -> HTMLResponse:
    """Return the start page."""
    return _TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {"form_base": "base.html", "title": _("Search")},
        headers={"Cache-Control": f"max-age={_MAX_AGE}"},
    )


def _parse_params(request: Request) -> tuple[str, SearchMode, int]:
    try:
        query = request.query_params["q"].strip()
    except KeyError as e:
        raise HTTPException(400, _("No search term was received")) from e
    if not query:
        raise HTTPException(400, _("The search term is empty"))

    try:
        mode = SearchMode(request.query_params["mode"])
    except (ValueError, KeyError) as e:
        raise HTTPException(400, _("Invalid search mode")) from e

    try:
        page = int(request.query_params["page"])
    except (ValueError, KeyError) as e:
        raise HTTPException(400, _("Invalid page number")) from e

    return query, mode, page


def search(request: Request) -> Response:
    """Perform a search and return the search result page."""
    query, mode, page = _parse_params(request)

    return _TEMPLATES.TemplateResponse(
        request,
        "search.html",
        {
            "form_base": "htmx.html"
            if "HX-Request" in request.headers
            else "base.html",
            "title": query,
            "query": query,
            "mode": mode,
            "page": page,
            "load": True,
        },
        headers={"Cache-Control": f"max-age={_MAX_AGE}"},
    )


@aiocache.cached(noself=True, ttl=_MAX_AGE)
@timed
async def _engine_search(
    state: _State, engine: Engine, query: ParsedQuery, page: int
) -> list[Result]:
    _CTX_ENGINE.set(engine)
    return await engine.search(state.session, query, page)  # type: ignore[attr-defined]


async def results(request: Request) -> Response:
    """Perform a search and return the search result page."""
    query, mode, page = _parse_params(request)

    parsed_query = _QUERY_PARSER.parse_query(
        query, request.headers.get("Accept-Language", "")
    )

    engines = get_engines(parsed_query, mode, page)

    results = {}
    errors = {}

    max_time = await timed_wait(
        {
            asyncio.create_task(
                _engine_search(request.state, engine, parsed_query, page)
            )
            for engine in engines
            if engine.weight > 1
        },
        _CTX_ENGINE,
        results,
        errors,
    )
    await timed_wait(
        {
            asyncio.create_task(
                _engine_search(request.state, engine, parsed_query, page)
            )
            for engine in engines
            if engine.weight <= 1
        },
        _CTX_ENGINE,
        results,
        errors,
        max(1.33, max_time) * 0.5,
    )

    rated_results = list(rate_results(results, parsed_query.lang))
    rated_results.sort(reverse=True)
    del rated_results[MAX_RESULTS:]

    return _TEMPLATES.TemplateResponse(
        request,
        "results.html",
        {
            "form_base": None if "HX-Request" in request.headers else "base.html",
            "results_base": "htmx.html"
            if "HX-Request" in request.headers
            else "search.html",
            "title": query,
            "query": query,
            "mode": mode,
            "page": page,
            "parsed_query": parsed_query,
            "results": rated_results,
            "engine_errors": errors,
        },
        headers={"Vary": "Accept-Language", "Cache-Control": f"max-age={_MAX_AGE}"},
    )


async def img(request: Request) -> Response:
    """Proxy an image."""
    url = request.query_params.get("url", None)
    if url is None:
        raise HTTPException(404, "Not Found")

    sha = request.query_params.get("sha", None)
    if sha is None or gen_sha(url) != sha:
        raise HTTPException(401, "Unauthorized")

    async with AsyncSession(impersonate="chrome") as session:
        try:
            resp = await session.get(url, headers={"Accept": "image/*"})
        except curl_cffi.CurlError as e:
            raise HTTPException(500, str(e)) from e

    if not (200 <= resp.status_code < 300):
        raise HTTPException(resp.status_code, resp.reason)

    if not resp.headers.get("Content-Type", "").startswith("image/"):
        raise HTTPException(500, "Not an image")

    return Response(
        content=resp.content,
        media_type=resp.headers["Content-Type"],
        headers={"Cache-Control": f"max-age={_MAX_AGE*10}"},
    )


def opensearch(request: Request) -> HTMLResponse:
    """Return opensearch.xml."""
    return _TEMPLATES.TemplateResponse(
        request, "opensearch.xml", media_type="application/xml"
    )


app = Starlette(
    lifespan=_lifespan,
    routes=[
        Route("/", endpoint=index),
        Route("/search", endpoint=search),
        Route("/results", endpoint=results),
        Route("/img", endpoint=img),
        Route("/opensearch.xml", endpoint=opensearch),
        Mount("/static", app=StaticFiles(directory="static"), name="static"),
    ],
    exception_handlers={HTTPException: http_exception},
)
