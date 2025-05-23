"""Module to perform a search."""

from enum import Flag, auto
from types import ModuleType
from typing import NamedTuple, Optional

import curl_cffi
import searx
import searx.data
import searx.enginelib
import searx.engines
import searx.result_types

from .common import Search, SearchMode
from .results import Result, result_from_searx
from .url import URL


class EngineFeatures(Flag):
    """Flags for engine features."""

    PAGING = auto()
    QUOTES = auto()
    SITE = auto()


def _required_features(search: Search) -> EngineFeatures:
    extensions = EngineFeatures(0)

    if search.page != 1:
        extensions |= EngineFeatures.PAGING

    if any(" " in word for word in search.words):
        extensions |= EngineFeatures.QUOTES

    if search.site is not None:
        extensions |= EngineFeatures.SITE

    return extensions


class EngineResults(NamedTuple):
    """Class to hold the results of a search w/ additional metadata."""

    engine: "Engine"
    results: list[Result]
    elapsed: float


_DEFAULT_FEATURES = EngineFeatures(0)


def _typed[T](v: object, t: type[T]) -> T:
    assert isinstance(v, t)
    return v


class Engine:
    """Class for a searx engine."""

    def __init__(
        self,
        settings: dict,
        *,
        mode: Optional[SearchMode] = None,
        page_size: Optional[int] = None,
        weight: float = 1.0,
        features: EngineFeatures = _DEFAULT_FEATURES,
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

        self.page_size = self._engine.page_size if page_size is None else page_size

        self.weight = weight

        self.features = features
        if self._engine.paging:
            self.features |= EngineFeatures.PAGING

    @property
    def url(self) -> URL:
        """Return URL of the engine."""
        return URL.parse(
            self._engine.about["website"]
            if "website" in self._engine.about
            else self._engine.search_url
        )

    @property
    def language_support(self) -> bool:
        """Check if the engine has language support."""
        return self._engine.language_support

    def supports_language(self, language: str) -> bool:
        """Check if the engine supports a query language."""
        if not self.language_support:
            return True
        return self._engine.traits.is_locale_supported(language)

    async def search(
        self,
        session: curl_cffi.AsyncSession,
        search: Search,
    ) -> EngineResults:
        """Perform a search and return the results."""
        params = self._engine.request(  # type: ignore[attr-defined]
            search.query_string(),
            {
                "cookies": {},
                "data": None,
                "headers": {},
                "language": search.lang,
                "method": "GET",
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
        response.raise_for_status()
        assert response.text

        response.url = URL.parse(response.url)
        response.search_params = params

        results: list[Result] = []

        for result in self._engine.response(response):  # type: ignore[attr-defined]
            parsed_result = result_from_searx(result)
            if parsed_result is not None:
                results.append(parsed_result)

        return EngineResults(self, results, response.elapsed)

    @property
    def name(self) -> str:
        """Return name of the engine in PascalCase."""
        return self._engine.name.title().replace(" ", "")

    def __str__(self) -> str:
        """Return name of engine."""
        return self.name


def _find_engine(name: str) -> dict:
    for engine in searx.settings["engines"]:
        if engine["name"] == name:
            return engine
    msg = f"Failed to find engine {name}"
    raise ValueError(msg)


_YEP = _find_engine("yep")
ENGINES = {
    Engine(_find_engine("alexandria"), page_size=10, features=EngineFeatures.SITE),
    Engine(_find_engine("bing"), page_size=10, weight=1.5),
    Engine(
        _find_engine("google"),
        page_size=10,
        weight=1.5,
        features=EngineFeatures.QUOTES | EngineFeatures.SITE,
    ),
    Engine(
        _find_engine("mojeek"),
        page_size=10,
        weight=1.5,
        features=EngineFeatures.SITE,
    ),
    Engine(_find_engine("reddit"), weight=0.25, mode=SearchMode.WEB),
    Engine(
        _find_engine("right dao"),
        features=EngineFeatures.QUOTES | EngineFeatures.SITE,
    ),
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
        page_size=12,
        features=EngineFeatures.SITE,
    ),
    Engine(
        _find_engine("stract"),
        page_size=20,
        features=EngineFeatures.QUOTES | EngineFeatures.SITE,
    ),
    Engine(_YEP, page_size=20, features=EngineFeatures.SITE),
    Engine(_find_engine("google scholar"), page_size=10, weight=1.5),
    Engine(
        _find_engine("bing images"),
        page_size=35,
        weight=1.5,
        features=EngineFeatures.SITE,
    ),
    Engine(_YEP, page_size=60, mode=SearchMode.IMAGES, features=EngineFeatures.SITE),
    Engine(
        _find_engine("google images"),
        page_size=100,
        weight=1.5,
        features=EngineFeatures.QUOTES | EngineFeatures.SITE,
    ),
}


def get_engines(search: Search) -> set[Engine]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for engine in ENGINES
        if engine.mode == search.mode
        if engine.supports_language(search.lang)
        if _required_features(search)
        in engine.features
        | (
            EngineFeatures.SITE
            if search.site == engine.url.host.removeprefix("www.")
            else EngineFeatures(0)
        )
    }
