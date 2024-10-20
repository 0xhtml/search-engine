"""Custom (meta) search engine."""

import asyncio
import contextlib
import gettext
import traceback
from typing import TYPE_CHECKING, AsyncIterator, TypedDict

import aiocache
import curl_cffi
import jinja2
from curl_cffi.requests import AsyncSession
from starlette.applications import Starlette
from starlette.datastructures import QueryParams
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


class _State(TypedDict):
    session: AsyncSession


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[_State]:
    async with AsyncSession(impersonate="chrome") as session:
        yield {"session": session}


class _HTMLError(Exception):
    def __init__(self, message: str, status_code: int = 200) -> None:
        self.message = message
        self.status_code = status_code

    def response(self, request: Request) -> Response:
        if "HX-Request" in request.headers:
            return _TEMPLATES.TemplateResponse(
                request,
                "error.html",
                {
                    "base": "htmx.html",
                    "title": _("Error"),
                    "error_message": self.message,
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
                    "error_message": self.message,
                },
                self.status_code,
            )
        return Response(self.message, self.status_code, media_type="text/plain")


def page_not_found(request: Request, exception: Exception) -> Response:
    """Return 404 error page."""
    return _HTMLError(_("The requested page was not not found"), 404).response(request)


def index(request: Request) -> HTMLResponse:
    """Return the start page."""
    return _TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {"form_base": "base.html", "title": _("Search")},
        headers={"Cache-Control": f"max-age={_MAX_AGE}"},
    )


def _parse_params(params: QueryParams) -> tuple[str, SearchMode, int]:
    try:
        query = params["q"].strip()
    except KeyError as e:
        raise _HTMLError(_("No search term was received"), 400) from e
    if not query:
        raise _HTMLError(_("The search term is empty"), 400)

    try:
        mode = SearchMode(params["mode"])
    except (ValueError, KeyError) as e:
        raise _HTMLError(_("Invalid search mode"), 400) from e

    try:
        page = int(params["page"])
    except (ValueError, KeyError) as e:
        raise _HTMLError(_("Invalid page number"), 400) from e

    return query, mode, page


def search(request: Request) -> Response:
    """Perform a search and return the search result page."""
    try:
        query, mode, page = _parse_params(request.query_params)
    except _HTMLError as e:
        return e.response(request)

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


class _EngineError(Exception):
    def __init__(self, engine: Engine, exc: BaseException) -> None:
        self.engine = engine
        self.exc = exc

    def __str__(self) -> str:
        return f"{self.engine}: {traceback.format_exception_only(self.exc)[0]}"


@aiocache.cached(noself=True, ttl=_MAX_AGE)
async def _engine_search(
    state: _State, engine: Engine, query: ParsedQuery, page: int
) -> tuple[Engine, list[Result]]:
    try:
        return engine, await engine.search(state.session, query, page)  # type: ignore[attr-defined]
    except BaseException as e:
        if not isinstance(e, asyncio.CancelledError):
            traceback.print_exc()
        raise _EngineError(engine, e) from e


async def results(request: Request) -> Response:
    """Perform a search and return the search result page."""
    try:
        query, mode, page = _parse_params(request.query_params)
    except _HTMLError as e:
        return e.response(request)

    parsed_query = _QUERY_PARSER.parse_query(
        query, request.headers.get("Accept-Language", "")
    )

    engines = get_engines(parsed_query, mode, page)
    important_engines = {engine for engine in engines if engine.weight > 1}

    errors = set()
    results = []

    tasks = {
        asyncio.create_task(_engine_search(request.state, engine, parsed_query, page))
        for engine in engines
    }

    while tasks:
        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                results.append(task.result())
            except _EngineError as e:
                errors.add(e)
        if (
            {engine for engine, engine_results in results}
            | {error.engine for error in errors}
        ) >= important_engines:
            break

    if tasks:
        await asyncio.wait(tasks, timeout=0.5)

    for task in tasks:
        task.cancel()
        try:
            results.append(await task)
        except _EngineError as e:
            errors.add(e)

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
        return _HTMLError("Not Found", 404).response(request)

    sha = request.query_params.get("sha", None)
    if sha is None or gen_sha(url) != sha:
        return _HTMLError("Unauthorized", 401).response(request)

    async with AsyncSession(impersonate="chrome") as session:
        try:
            resp = await session.get(url, headers={"Accept": "image/*"})
        except curl_cffi.CurlError as e:
            return _HTMLError(str(e), 500).response(request)

    if not (200 <= resp.status_code < 300):
        return _HTMLError(
            f"{resp.status_code} {resp.reason}", resp.status_code
        ).response(request)

    if not resp.headers.get("Content-Type", "").startswith("image/"):
        return _HTMLError("Not an image", 500).response(request)

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
    exception_handlers={404: page_not_found},
)
