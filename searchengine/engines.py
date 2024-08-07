"""Module to perform a search."""

from . import importer  # isort: skip

import json
from enum import Enum
from types import ModuleType
from typing import Any, ClassVar, Optional, Type, TypeAlias
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
from .results import AnswerResult, ImageResult, Result, WebResult

bing.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing"])
bing_images.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing images"])
google.traits = EngineTraits(**searx.data.ENGINE_TRAITS["google"])
google_images.traits = EngineTraits(**searx.data.ENGINE_TRAITS["google images"])


class _LoggerMixin:
    def __init__(self, name: str) -> None:
        self.name = name

    def debug(self, msg: str, *args: list) -> None:
        print(f"[!] [{self.name.capitalize()}] {msg % args}")


bing.logger = _LoggerMixin("bing")
google.logger = _LoggerMixin("google")


class SearchMode(Enum):
    """Search mode determining which type of results to return."""

    WEB = "web"
    IMAGES = "images"


class EngineError(Exception):
    """Exception that is raised when a request fails."""

    def __init__(self, engine: type["Engine"], msg: str) -> None:
        """Initialize the exception."""
        self.engine = engine
        super().__init__(msg)


class _EngineRequestError(EngineError):
    def __init__(self, engine: type["Engine"], error: httpx.RequestError) -> None:
        super().__init__(engine, f"Request error on search ({type(error).__name__})")


class _EngineStatusError(EngineError):
    def __init__(self, engine: type["Engine"], status: int, reason: str) -> None:
        super().__init__(engine, f"Didn't receive status code 2xx ({status} {reason})")


class Engine:
    """Base class for a search engine."""

    WEIGHT: ClassVar = 1.0
    SUPPORTED_LANGUAGES: ClassVar[Optional[set[str]]] = None
    QUERY_EXTENSIONS: ClassVar[QueryExtensions] = QueryExtensions.SITE
    MODE: ClassVar[SearchMode] = SearchMode.WEB

    _METHOD: ClassVar[str] = "GET"
    _HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0",
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
        cls,
        client: httpx.AsyncClient,
        query: ParsedQuery,
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
            raise _EngineRequestError(cls, e) from e

        if not response.is_success:
            raise _EngineStatusError(cls, response.status_code, response.reason_phrase)

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

        results: list[Result] = []

        for result in cls._iter(root, cls._RESULT_PATH):
            title = cls._get(result, cls._TITLE_PATH)
            assert title

            _url = cls._get(result, cls._URL_PATH)
            assert _url
            url = httpx.URL(_url)

            text = cls._get(result, cls._TEXT_PATH)

            if cls.MODE == SearchMode.IMAGES:
                src = cls._get(result, cls._SRC_PATH)
                assert src
                results.append(ImageResult(title, url, text or None, httpx.URL(src)))
                continue

            results.append(WebResult(title, url, text or None))

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
        return html.document_fromstring(response.text)

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
            elems[0],
            encoding="unicode",
            method="text",
            with_tail=False,
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

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        cls._ENGINE.search_type = cls.MODE.value  # type: ignore[attr-defined]
        if cls._ENGINE == mojeek and cls.MODE == SearchMode.WEB:  # noqa: SIM300
            cls._ENGINE.search_type = ""  # type: ignore[attr-defined]
        return cls._ENGINE.request(str(query), params)

    @classmethod
    def _response(cls, response: httpx.Response) -> list[Result]:
        if not response.text:
            return []

        results: list[Result] = []

        for result in cls._ENGINE.response(response):
            if "number_of_results" in result or "suggestion" in result:
                continue

            assert "url" in result
            assert isinstance(result["url"], str)
            assert result["url"]

            url = httpx.URL(result["url"])

            if "answer" in result:
                assert isinstance(result["answer"], str)
                assert result["answer"]
                results.append(AnswerResult(result["answer"], url))
                continue

            assert "title" in result
            assert isinstance(result["title"], str)
            assert result["title"]

            if "img_src" in result:
                assert isinstance(result["img_src"], str)
                assert result["img_src"]
                assert result.get("template") == "images.html"
                results.append(
                    ImageResult(
                        result["title"],
                        url,
                        result.get("content") or None,
                        httpx.URL(result["img_src"]),
                    )
                )
                continue

            assert "content" in result
            assert isinstance(result["content"], str)
            results.append(
                WebResult(
                    result["title"],
                    url,
                    result["content"] or None,
                )
            )

        return results


class Bing(SearxEngine):
    """Search on Bing."""

    WEIGHT = 1.3
    _ENGINE = bing


class BingImages(Bing):
    """Search images on Bing."""

    MODE = SearchMode.IMAGES
    _ENGINE = bing_images


class Mojeek(SearxEngine):
    """Search on Mojeek."""

    _ENGINE = mojeek


class MojeekImages(Mojeek):
    """Search images on Yep."""

    QUERY_EXTENSIONS = QueryExtensions(0)
    MODE = SearchMode.IMAGES


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

    MODE = SearchMode.IMAGES
    QUERY_EXTENSIONS = QueryExtensions(0)


class SeSe(JSONEngine):
    """Search on SeSe."""

    _URL = "https://se-proxy.azurewebsites.net/api/search"

    _PARAMS = {"slice": "0:12"}

    _RESULT_PATH = jsonpath_ng.ext.parse("'结果'[?'信息'.'标题' != '']")
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

    MODE = SearchMode.IMAGES
    _ENGINE = google_images


class Reddit(SearxEngine):
    """Search on Reddit."""

    WEIGHT = 0.7
    QUERY_EXTENSIONS = QueryExtensions(0)
    _ENGINE = reddit


_ENGINES = {
    Alexandria,
    Bing,
    BingImages,
    Google,
    GoogleImages,
    Mojeek,
    MojeekImages,
    Reddit,
    RightDao,
    SeSe,
    Stract,
    Yep,
    YepImages,
}


def get_engines(mode: SearchMode, query: ParsedQuery) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for engine in _ENGINES
        if engine.MODE == mode
        if engine.SUPPORTED_LANGUAGES is None
        or query.lang in engine.SUPPORTED_LANGUAGES
        if query.required_extensions() in engine.QUERY_EXTENSIONS
    }
