"""Module to perform a search."""

from . import importer

import contextlib
import json
from enum import Enum
from types import ModuleType
from typing import Any, ClassVar, NamedTuple, Optional, Type, TypeAlias
from urllib.parse import urlencode

import httpx
import jsonpath_ng
import jsonpath_ng.ext
import searx.data
from lxml import etree, html
from searx.enginelib.traits import EngineTraits
from searx.engines import (
    bing,
    bing_images,
    google,
    google_images,
    mojeek,
    reddit,
    stract,
    yep,
)

from .query import ParsedQuery, QueryExtensions

bing.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing"])
bing_images.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing images"])
google.traits = EngineTraits(**searx.data.ENGINE_TRAITS["google"])
google_images.traits = EngineTraits(**searx.data.ENGINE_TRAITS["google images"])


class _LoggerMixin:
    def __init__(self, name: str):
        self.name = name

    def debug(self, msg: str, *args: list) -> None:
        print(f"[!] [{self.name.capitalize()}] {msg % args}")


bing.logger = _LoggerMixin("bing")
google.logger = _LoggerMixin("google")


class SearchMode(Enum):
    """Search mode determining which type of results to return."""

    WEB = "web"
    IMAGES = "images"


class Result(NamedTuple):
    """Single result returned by a search."""

    @classmethod
    def from_dict(cls, result: dict[str, str]) -> "Result":
        """Convert a dict returned by searx into a result tuple."""
        return cls(
            result["title"],
            httpx.URL(result["url"]),
            result["content"] or None,
            result.get("img_src"),
        )

    title: str
    url: httpx.URL
    text: Optional[str]
    src: Optional[str]


class EngineError(Exception):
    """Exception that is raised when a request fails."""


class _EngineRequestError(EngineError):
    def __init__(self, error: httpx.RequestError):
        super().__init__(f"Request error on search ({type(error).__name__})")


class _EngineStatusError(EngineError):
    def __init__(self, status: int, reason: str):
        super().__init__(f"Didn't receive status code 2xx ({status} {reason})")


class Engine:
    """Base class for a search engine."""

    WEIGHT: ClassVar = 1.0
    SUPPORTED_LANGUAGES: ClassVar[Optional[set[str]]] = None
    QUERY_EXTENSIONS: ClassVar[QueryExtensions] = QueryExtensions.SITE

    _METHOD: ClassVar[str] = "GET"
    _HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0"
    }

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None) -> None:
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def _response(cls, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    @classmethod
    async def search(
        cls, client: httpx.AsyncClient, query: ParsedQuery
    ) -> list[Result]:
        """Perform a search and return the results."""
        params = {
            "searxng_locale": query.lang,
            "time_range": None,
            "pageno": 1,
            "safesearch": 2,
            "method": cls._METHOD,
            "headers": cls._HEADERS,
            "data": None,
            "cookies": {},
        }
        params = cls._request(query, params)

        assert isinstance(params["method"], str)
        assert isinstance(params["url"], str)
        assert isinstance(params["headers"], dict)
        assert isinstance(params["cookies"], dict)

        try:
            response = await client.request(
                params["method"],
                params["url"],
                headers=params["headers"],
                data=params["data"],
                cookies=params["cookies"],
            )
        except httpx.RequestError as e:
            raise _EngineRequestError(e) from e

        if not response.is_success:
            raise _EngineStatusError(response.status_code, response.reason_phrase)

        response.search_params = params  # type: ignore[attr-defined]
        return cls._response(response)


Path: TypeAlias = etree.XPath | jsonpath_ng.JSONPath
Element: TypeAlias = html.HtmlElement | dict


class CstmEngine(Engine):
    """Base class for a custom search engine."""

    _URL: ClassVar[str]

    _PARAMS: ClassVar[dict[str, str | bool]] = {}
    _QUERY_KEY: ClassVar[str] = "q"

    _RESULT_PATH: ClassVar[Path]
    _TITLE_PATH: ClassVar[Path]
    _URL_PATH: ClassVar[Path]
    _TEXT_PATH: ClassVar[Optional[Path]] = None
    _SRC_PATH: ClassVar[Optional[Path]] = None

    @staticmethod
    def _parse_response(response: httpx.Response) -> Element:
        raise NotImplementedError

    @staticmethod
    def _iter(root: Element, path: Path) -> list[Element]:
        raise NotImplementedError

    @staticmethod
    def _get(root: Element, path: Optional[Path]) -> Optional[str]:
        raise NotImplementedError

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        data = {cls._QUERY_KEY: str(query), **cls._PARAMS}

        params["url"] = (
            f"{cls._URL}?{urlencode(data)}" if cls._METHOD == "GET" else cls._URL
        )
        params["data"] = json.dumps(data) if cls._METHOD == "POST" else None

        return params

    @classmethod
    def _response(cls, response: httpx.Response) -> list[Result]:
        root = cls._parse_response(response)

        results = []

        for result in cls._iter(root, cls._RESULT_PATH):
            if not (title := cls._get(result, cls._TITLE_PATH)):
                continue

            if not (url := cls._get(result, cls._URL_PATH)):
                continue

            text = cls._get(result, cls._TEXT_PATH)
            src = cls._get(result, cls._SRC_PATH)

            with contextlib.suppress(httpx.InvalidURL):
                results.append(Result(title, httpx.URL(url), text, src))

        return results


class XPathEngine(CstmEngine):
    """Base class for a x-path search engine."""

    _HEADERS = {
        **CstmEngine._HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    @staticmethod
    def _parse_response(response: httpx.Response) -> html.HtmlElement:
        return etree.fromstring(response.text, parser=html.html_parser)

    @staticmethod
    def _iter(root: html.HtmlElement, path: etree.XPath) -> list[html.HtmlElement]:
        elems = path(root)
        assert isinstance(elems, list)
        assert all(isinstance(elem, html.HtmlElement) for elem in elems)
        return elems

    @staticmethod
    def _get(root: html.HtmlElement, path: Optional[etree.XPath]) -> Optional[str]:
        if path is None or not (elems := path(root)):
            return None
        assert isinstance(elems, list)
        if isinstance(elems[0], str):
            return elems[0]
        return html.tostring(
            elems[0], encoding="unicode", method="text", with_tail=False
        )


class JSONEngine(CstmEngine):
    """Base class for search engine using JSON."""

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict:
        return response.json()

    @staticmethod
    def _iter(root: dict, path: jsonpath_ng.JSONPath) -> list[dict]:
        return path.find(root)

    @staticmethod
    def _get(root: dict, path: Optional[jsonpath_ng.JSONPath]) -> Optional[str]:
        if path is None or not (elems := path.find(root)):
            return None
        return elems[0].value


class SearxEngine(Engine):
    """Class for a engine defined in searxng."""

    _ENGINE: ClassVar[ModuleType]
    _MODE: ClassVar[SearchMode] = SearchMode.WEB

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        cls._ENGINE.search_type = cls._MODE.value  # type: ignore[attr-defined]
        if cls._ENGINE == mojeek and cls._MODE == SearchMode.WEB:  # noqa: SIM300
            cls._ENGINE.search_type = ""  # type: ignore[attr-defined]
        return cls._ENGINE.request(str(query), params)

    @classmethod
    def _response(cls, response: httpx.Response) -> list[Result]:
        if response.text == "":
            return []

        results = []

        for result in cls._ENGINE.response(response):
            try:
                if (
                    "number_of_results" in result
                    or "answer" in result
                    or "suggestion" in result
                ):
                    continue

                assert result["url"]

                if cls._MODE != SearchMode.IMAGES and "img_src" in result:
                    continue

                if cls._MODE == SearchMode.WEB:
                    assert result["title"]
                    assert "img_src" not in result
                    assert "thumbnail_src" not in result
                    assert result.get("template", "default.html") == "default.html"
                elif cls._MODE == SearchMode.IMAGES:
                    assert "title" in result
                    assert result["img_src"]
                    assert "thumbnail_src" not in result or result["thumbnail_src"]
                    assert result["template"] == "images.html"
                else:
                    raise ValueError(f"Unknown mode: {cls._MODE}")

                results.append(Result.from_dict(result))
            except (KeyError, AssertionError, httpx.InvalidURL) as e:
                cls._log(f"{type(e).__name__} {e} on {result}")

        return results


class Bing(SearxEngine):
    """Search on Bing."""

    WEIGHT = 1.3
    _ENGINE = bing


class BingImages(Bing):
    """Search images on Bing."""

    _ENGINE = bing_images


class Mojeek(SearxEngine):
    """Search on Mojeek."""

    _ENGINE = mojeek


class MojeekImages(Mojeek):
    """Search images on Yep."""

    QUERY_EXTENSIONS = QueryExtensions(0)

    _MODE = SearchMode.IMAGES


class Stract(SearxEngine):
    """Search on stract."""

    # TODO: region selection doesn't really work
    SUPPORTED_LANGUAGES = {"en"}
    QUERY_EXTENSIONS = QueryExtensions.QUOTES | QueryExtensions.SITE

    _ENGINE = stract


class RightDao(XPathEngine):
    """Search on Right Dao."""

    SUPPORTED_LANGUAGES = {"en"}
    QUERY_EXTENSIONS = QueryExtensions.QUOTES | QueryExtensions.SITE

    _URL = "https://rightdao.com/search"

    _RESULT_PATH = etree.XPath('//div[@class="description"]')
    _TITLE_PATH = etree.XPath('../div[@class="title"]')
    _URL_PATH = etree.XPath('../div[@class="title"]/a/@href')
    _TEXT_PATH = etree.XPath(".")


class Alexandria(JSONEngine):
    """Search on Alexandria an English only search engine."""

    SUPPORTED_LANGUAGES = {"en"}

    _URL = "https://api.alexandria.org"

    _PARAMS = {"a": "1", "c": "a"}

    _RESULT_PATH = jsonpath_ng.ext.parse("results[*]")
    _TITLE_PATH = jsonpath_ng.parse("title")
    _URL_PATH = jsonpath_ng.parse("url")
    _TEXT_PATH = jsonpath_ng.parse("snippet")


class Yep(SearxEngine):
    """Search on Yep."""

    _ENGINE = yep


class YepImages(Yep):
    """Search images on Yep."""

    QUERY_EXTENSIONS = QueryExtensions(0)

    _MODE = SearchMode.IMAGES


class SeSe(JSONEngine):
    """Search on SeSe."""

    _URL = "https://se-proxy.azurewebsites.net/api/search"

    _PARAMS = {"slice": "0:12"}

    _RESULT_PATH = jsonpath_ng.ext.parse("'结果'[*]")
    _URL_PATH = jsonpath_ng.parse("'网址'")
    _TITLE_PATH = jsonpath_ng.parse("'信息'.'标题'")
    _TEXT_PATH = jsonpath_ng.parse("'信息'.'描述'")


class Google(SearxEngine):
    """Search on Google."""

    WEIGHT = 1.3
    QUERY_EXTENSIONS = QueryExtensions.QUOTES | QueryExtensions.SITE

    _ENGINE = google


class GoogleImages(Google):
    """Search images on Google."""

    _ENGINE = google_images
    _MODE = SearchMode.IMAGES


class Reddit(SearxEngine):
    """Search on Reddit."""

    QUERY_EXTENSIONS = QueryExtensions(0)

    _ENGINE = reddit


_MODE_MAP: dict[SearchMode, set[Type[Engine]]] = {
    SearchMode.WEB: {
        Alexandria,
        Bing,
        Google,
        Mojeek,
        Reddit,
        RightDao,
        SeSe,
        Stract,
        Yep,
    },
    SearchMode.IMAGES: {BingImages, MojeekImages, YepImages, GoogleImages},
}


def get_engines(mode: SearchMode, query: ParsedQuery) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for engine in _MODE_MAP.get(mode, set())
        if engine.SUPPORTED_LANGUAGES is None
        or query.lang in engine.SUPPORTED_LANGUAGES
        if query.required_extensions() in engine.QUERY_EXTENSIONS
    }
