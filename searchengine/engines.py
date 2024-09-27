"""Module to perform a search."""

from . import importer  # isort: skip

import json
from types import ModuleType
from typing import Any, ClassVar, Optional, Type, TypeAlias
from urllib.parse import urlencode, urljoin

import curl_cffi
import jsonpath_ng
import jsonpath_ng.ext
import searx
import searx.data
import searx.enginelib
import searx.engines
from curl_cffi.requests import AsyncSession, Response
from lxml import etree, html

from .query import ParsedQuery, QueryExtensions, SearchMode
from .results import AnswerResult, ImageResult, Result, WebResult
from .url import Url


def _load_searx_engine(name: str) -> searx.enginelib.Engine | ModuleType:
    """Load a searx engine."""
    for engine in searx.settings["engines"]:
        if engine["name"] == name:
            ret = searx.engines.load_engine(engine)
            if ret is None:
                raise ValueError(f"Failed to load searx engine {name}")
            return ret
    raise ValueError(f"Searx engine {name} not found")


class EngineError(Exception):
    """Exception that is raised when a request fails."""

    @classmethod
    def from_exception(cls, engine: type["Engine"], error: Exception) -> "EngineError":
        """Create an exception from another exception."""
        msg = str(type(error).__name__)
        if str(error):
            msg += f": {error}"
        return cls(engine, msg)

    @classmethod
    def from_status(cls, engine: type["Engine"], response: Response) -> "EngineError":
        """Create an exception from a response status."""
        return cls(
            engine,
            "Didn't receive status code 2xx "
            f"({response.status_code} {response.reason})",
        )

    def __init__(self, engine: type["Engine"], msg: str) -> None:
        """Initialize the exception."""
        self.engine = engine
        super().__init__(msg)


class Engine:
    """Base class for a search engine."""

    WEIGHT: ClassVar = 1.0
    SUPPORTED_LANGUAGES: ClassVar[Optional[set[str]]] = None
    QUERY_EXTENSIONS: ClassVar[QueryExtensions] = QueryExtensions.SITE
    MODE: ClassVar[SearchMode] = SearchMode.WEB

    _METHOD: ClassVar[str] = "GET"
    _HEADERS: ClassVar[dict[str, str]] = {}

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
    def _response(cls, response: Response) -> list[Result]:
        raise NotImplementedError

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
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
        assert isinstance(params["data"], str) or params["data"] is None

        try:
            response = await session.request(
                params["method"],
                params["url"],
                headers=params["headers"],
                data=params["data"],
                cookies=params["cookies"],
            )
        except curl_cffi.CurlError as e:
            raise EngineError.from_exception(cls, e) from e

        if not (200 <= response.status_code < 300):
            raise EngineError.from_status(cls, response)

        response.search_params = params  # type: ignore[attr-defined]
        response.url = Url(response.url)
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
    def _parse_response(response: Response) -> Element:
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
    def _response(cls, response: Response) -> list[Result]:
        root = cls._parse_response(response)

        results: list[Result] = []

        for result in cls._iter(root, cls._RESULT_PATH):
            title = cls._get(result, cls._TITLE_PATH)
            assert title

            _url = cls._get(result, cls._URL_PATH)
            assert _url
            url = Url(urljoin(str(response.url), _url))

            text = cls._get(result, cls._TEXT_PATH)

            if cls.MODE == SearchMode.IMAGES:
                src = cls._get(result, cls._SRC_PATH)
                assert src
                results.append(ImageResult(title, url, text or None, Url(src)))
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
    def _parse_response(response: Response) -> html.HtmlElement:
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
    def _parse_response(response: Response) -> dict:
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
        if cls._ENGINE.name == "mojeek" and cls.MODE == SearchMode.WEB:
            cls._ENGINE.search_type = ""  # type: ignore[attr-defined]
        return cls._ENGINE.request(str(query), params)

    @classmethod
    def _response(cls, response: Response) -> list[Result]:
        if not response.text:
            return []

        results: list[Result] = []

        for result in cls._ENGINE.response(response):
            if "number_of_results" in result or "suggestion" in result:
                continue

            assert "url" in result
            assert isinstance(result["url"], str)
            if not result["url"]:
                continue

            url = Url(result["url"])

            if "answer" in result:
                assert isinstance(result["answer"], str)
                assert result["answer"]
                results.append(AnswerResult(result["answer"], url))
                continue

            assert "title" in result
            assert isinstance(result["title"], str)

            if "img_src" in result:
                src = result.get("thumbnail_src", result["img_src"])
                assert isinstance(src, str)
                assert src
                assert result.get("template") == "images.html"
                results.append(
                    ImageResult(
                        result["title"],
                        url,
                        result.get("content") or None,
                        Url(src),
                    )
                )
                continue

            assert result["title"]
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
    _ENGINE = _load_searx_engine("bing")


class BingImages(Bing):
    """Search images on Bing."""

    MODE = SearchMode.IMAGES
    _ENGINE = _load_searx_engine("bing images")


class Mojeek(SearxEngine):
    """Search on Mojeek."""

    _ENGINE = _load_searx_engine("mojeek")


class MojeekImages(Mojeek):
    """Search images on Yep."""

    QUERY_EXTENSIONS = QueryExtensions(0)
    MODE = SearchMode.IMAGES


class Stract(SearxEngine):
    """Search on stract."""

    # TODO: region selection doesn't really work
    SUPPORTED_LANGUAGES = {"en"}
    QUERY_EXTENSIONS = QueryExtensions.QUOTES | QueryExtensions.SITE
    _ENGINE = _load_searx_engine("stract")


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

    _ENGINE = _load_searx_engine("yep")


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
    _ENGINE = _load_searx_engine("google")


class GoogleImages(Google):
    """Search images on Google."""

    MODE = SearchMode.IMAGES
    _ENGINE = _load_searx_engine("google images")


class Reddit(SearxEngine):
    """Search on Reddit."""

    WEIGHT = 0.7
    QUERY_EXTENSIONS = QueryExtensions(0)
    _ENGINE = _load_searx_engine("reddit")


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


def get_engines(query: ParsedQuery) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for engine in _ENGINES
        if engine.MODE == query.mode
        if engine.SUPPORTED_LANGUAGES is None
        or query.lang in engine.SUPPORTED_LANGUAGES
        if query.required_extensions() in engine.QUERY_EXTENSIONS
    }
