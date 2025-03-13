"""Module to perform a search."""

from enum import Flag, auto
from http import HTTPStatus
from types import ModuleType
from typing import Any, Optional
from urllib.parse import ParseResult, urlparse

import searx
import searx.data
import searx.enginelib
import searx.engines
import searx.result_types
from curl_cffi.requests import AsyncSession, Response
from curl_cffi.requests.session import HttpMethod

from .common import Search, SearchMode
from .results import Result, result_from_searx


class _Features(Flag):
    PAGING = auto()
    QUOTES = auto()
    SITE = auto()


def _required_features(search: Search) -> _Features:
    extensions = _Features(0)

    if search.page != 1:
        extensions |= _Features.PAGING

    if any(" " in word for word in search.words):
        extensions |= _Features.QUOTES

    if search.site is not None:
        extensions |= _Features.SITE

    return extensions


class StatusCodeError(Exception):
    """Exception that is raised if a request to an engine doesn't return 2xx."""

    def __init__(self, response: Response) -> None:
        """Initialize the exception w/ an Response object."""
        super().__init__(f"{response.status_code} {response.reason}")


_DEFAULT_FEATURES = _Features(0)


def _typed[T](v: Any, t: type[T]) -> T:
    assert isinstance(v, t)
    return v


class Engine:
    """Class for a searx engine."""

    def __init__(
        self,
        settings: dict,
        *,
        mode: Optional[SearchMode] = None,
        weight: float = 1.0,
        features: _Features = _DEFAULT_FEATURES,
        method: HttpMethod = "GET",
    ) -> None:
        """Initialize engine."""
        self._engine = _typed(searx.engines.load_engine(settings), ModuleType)

        if mode is None:
            for _mode in SearchMode:
                if _mode.searx_category() in self._engine.categories:
                    self.mode = _mode
                    break
            else:
                msg = f"Failed to detect mode for {self._engine.name}"
                raise ValueError(msg)
        else:
            self.mode = mode
            self._engine.search_type = mode.value  # type: ignore[attr-defined]

        self.weight = weight

        self.features = features
        if self._engine.paging:
            self.features |= _Features.PAGING

        self._method = method

    @property
    def url(self) -> ParseResult:
        """Return URL of the engine."""
        return urlparse(
            self._engine.about["website"]
            if "website" in self._engine.about
            else self._engine.search_url
        )

    def supports_language(self, language: str) -> bool:
        """Check if the engine supports a query language."""
        if not self._engine.language_support:
            return True
        return self._engine.traits.is_locale_supported(language)

    async def search(self, session: AsyncSession, search: Search) -> list[Result]:
        """Perform a search and return the results."""
        params = self._engine.request(  # type: ignore[attr-defined]
            search.query_string(),
            {
                "cookies": {},
                "data": None,
                "headers": {},
                "language": search.lang,
                "method": self._method,
                "pageno": search.page,
                "safesearch": 2,
                "searxng_locale": search.lang,
                "time_range": None,
            },
        )

        response = await session.request(
            params["method"],
            params["url"],
            headers=params["headers"],
            data=params["data"],
            cookies=params["cookies"],
        )

        if not HTTPStatus(response.status_code).is_success:
            raise StatusCodeError(response)

        assert response.text

        class Url(ParseResult):
            @property
            def host(self) -> str:
                return self.netloc

        # TODO: wrap response instead
        response.url = Url(*urlparse(response.url))
        response.search_params = params

        results: list[Result] = []

        for result in self._engine.response(response):  # type: ignore[attr-defined]
            parsed_result = result_from_searx(result)
            if parsed_result is not None:
                results.append(parsed_result)

        return results

    def __str__(self) -> str:
        """Return name of engine in PascalCase."""
        return self._engine.name.title().replace(" ", "")


def _find_engine(name: str) -> dict:
    for engine in searx.settings["engines"]:
        if engine["name"] == name:
            return engine
    msg = f"Failed to find engine {name}"
    raise ValueError(msg)


_YEP = _find_engine("yep")
_ENGINES = {
    Engine(_find_engine("alexandria"), features=_Features.SITE),
    # TODO: check if bing does support quotation
    Engine(_find_engine("bing"), weight=1.5, features=_Features(0)),
    Engine(_find_engine("bing images"), weight=1.5, features=_Features.SITE),
    Engine(
        _find_engine("google"),
        weight=1.5,
        features=_Features.QUOTES | _Features.SITE,
    ),
    Engine(
        _find_engine("google images"),
        weight=1.5,
        features=_Features.QUOTES | _Features.SITE,
    ),
    Engine(_find_engine("google scholar"), weight=1.5),
    Engine(_find_engine("mojeek"), weight=1.5, features=_Features.SITE),
    Engine(_find_engine("reddit"), weight=0.25, mode=SearchMode.WEB),
    Engine(_find_engine("right dao"), features=_Features.QUOTES | _Features.SITE),
    Engine(
        {
            "name": "sese",
            "engine": "json_engine",
            "search_url": "https://se-proxy.azurewebsites.net/api/search?slice=0:12&q={query}",
            "results_query": "结果",
            "url_query": "网址",
            "title_query": "信息/标题",
            "content_query": "信息/描述",
        },
        features=_Features.SITE,
    ),
    Engine(_find_engine("stract"), features=_Features.QUOTES | _Features.SITE),
    Engine(_YEP, features=_Features.SITE),
    Engine(_YEP, mode=SearchMode.IMAGES, features=_Features.SITE),
}


def get_engines(search: Search) -> set[Engine]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for engine in _ENGINES
        if engine.mode == search.mode
        if engine.supports_language(search.lang)
        if _required_features(search)
        in engine.features
        | (
            _Features.SITE
            if search.site == engine.url.netloc.removeprefix("www.")
            else _Features(0)
        )
    }
