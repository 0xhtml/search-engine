"""Custom (meta) search engine."""

import contextlib
import gettext
from collections.abc import AsyncIterator, Callable
from http import HTTPStatus
from typing import TypedDict

import curl_cffi
from curl_cffi.requests import AsyncSession
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .common import Search, SearchMode
from .lang import detect_lang, parse_accept_language
from .query import parse_query
from .search import MAX_AGE, perform_search
from .sha import gen_sha
from .templates import TEMPLATES


def _translation(request: Request) -> Callable[[str], str]:
    languages = parse_accept_language(request.headers.get("Accept-Language", ""))
    translation = gettext.translation("messages", "locales", languages, fallback=True)
    return translation.gettext


class _State(TypedDict):
    session: AsyncSession


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncIterator[_State]:
    async with AsyncSession(impersonate="firefox") as session:
        yield {"session": session}


def http_exception(request: Request, exc: HTTPException) -> Response:
    """Handle HTTP exceptions."""
    _ = _translation(request)
    if "HX-Request" in request.headers:
        return TEMPLATES.TemplateResponse(
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
        return TEMPLATES.TemplateResponse(
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
    _ = _translation(request)
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {"_": _, "form_base": "base.html", "title": _("Search")},
        headers={"Cache-Control": f"max-age={MAX_AGE}", "Vary": "Accept-Language"},
    )


def _parse_params(request: Request) -> tuple[str, SearchMode, int]:
    _ = _translation(request)
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

    return TEMPLATES.TemplateResponse(
        request,
        "search.html",
        {
            "_": _translation(request),
            "form_base": "htmx.html"
            if "HX-Request" in request.headers
            else "base.html",
            "title": query,
            "query": query,
            "mode": mode,
            "page": page,
            "load": True,
        },
        headers={
            "Vary": "Accept-Language, HX-Request",
            "Cache-Control": f"max-age={MAX_AGE}",
        },
    )


async def results(request: Request) -> Response:
    """Perform a search and return the search result page."""
    query, mode, page = _parse_params(request)

    parsed_query = parse_query(query)

    lang = parsed_query.lang
    if lang is None:
        languages = parse_accept_language(request.headers.get("Accept-Language", ""))
        lang = detect_lang(" ".join(parsed_query.words), languages or ["en"])

    search = Search(parsed_query.words, lang, parsed_query.site, mode, page)

    rated_results, errors = await perform_search(request.state.session, search)

    return TEMPLATES.TemplateResponse(
        request,
        "results.html",
        {
            "_": _translation(request),
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
        headers={
            "Vary": "Accept-Language, HX-Request",
            "Cache-Control": f"max-age={MAX_AGE}",
        },
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

    if not HTTPStatus(resp.status_code).is_success:
        raise HTTPException(resp.status_code, resp.reason)

    if not resp.headers.get("Content-Type", "").startswith("image/"):
        raise HTTPException(500, "Not an image")

    return Response(
        content=resp.content,
        media_type=resp.headers["Content-Type"],
        headers={"Cache-Control": f"max-age={MAX_AGE * 10}"},
    )


def opensearch(request: Request) -> HTMLResponse:
    """Return opensearch.xml."""
    return TEMPLATES.TemplateResponse(
        request,
        "opensearch.xml",
        {"_": _translation(request)},
        media_type="application/xml",
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
