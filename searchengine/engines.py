"""Module to perform a search."""

from . import importer

import json
from enum import Enum
from typing import Any, ClassVar, Optional, Type, TypeVar, Union
from urllib.parse import urlencode

import httpx
import jsonpath_ng
import jsonpath_ng.ext
import searx.data
from lxml import etree, html
from searx.enginelib.traits import EngineTraits
from searx.engines import bing, bing_images, google, stract, yep

from .query import ParsedQuery, QueryExtensions
from .results import Result

bing.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing"])
bing_images.traits = EngineTraits(**searx.data.ENGINE_TRAITS["bing images"])
google.traits = EngineTraits(**searx.data.ENGINE_TRAITS["google"])


class _LoggerMixin:
    def __init__(self, name: str):
        self.name = name

    def debug(self, msg, *args) -> None:
        print(f"[!] [{self.name.capitalize()}] {msg % args}")


bing.logger = _LoggerMixin("bing")
google.logger = _LoggerMixin("google")


class SearchMode(Enum):
    WEB = "web"
    IMAGES = "images"


class EngineError(Exception):
    """Exception that is raised when a request fails."""


class Engine:
    """Base class for a search engine."""

    WEIGHT: ClassVar = 1.0
    SUPPORTED_LANGUAGES: ClassVar[Optional[set[str]]] = None
    QUERY_EXTENSIONS: ClassVar[QueryExtensions] = QueryExtensions.SITE

    _METHOD: ClassVar[str] = "GET"

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
            "headers": {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            },
            "data": None,
            "cookies": {},
        }
        params = cls._request(query, params)

        try:
            response = await client.request(
                params["method"],
                params["url"],
                headers=params["headers"],
                cookies=params["cookies"],
                data=params["data"],
            )
        except httpx.RequestError as e:
            raise EngineError(f"Request error on search ({type(e).__name__})") from e

        if not response.is_success:
            raise EngineError(
                "Didn't receive status code 2xx"
                f" ({response.status_code} {response.reason_phrase})",
            )

        response.search_params = params
        return cls._response(response)


T = TypeVar("T")
U = TypeVar("U")


class CstmEngine(Engine):
    """Base class for a custom search engine."""

    _URL: ClassVar[str]

    _PARAMS: ClassVar[dict[str, Union[str, bool]]] = {}
    _QUERY_KEY: ClassVar[str] = "q"

    _HEADERS: ClassVar[dict[str, str]] = {}

    _LANG_MAP: ClassVar[dict[str, str]]
    _LANG_KEY: ClassVar[str]

    _RESULT_PATH: ClassVar[U]
    _TITLE_PATH: ClassVar[U]
    _URL_PATH: ClassVar[U]
    _TEXT_PATH: ClassVar[Optional[U]] = None
    _SRC_PATH: ClassVar[Optional[U]] = None

    @staticmethod
    def _parse_response(response: httpx.Response) -> T:
        raise NotImplementedError

    @staticmethod
    def _iter(root: T, path: U) -> list[T]:
        raise NotImplementedError

    @staticmethod
    def _get(root: T, path: Optional[U]) -> Optional[str]:
        raise NotImplementedError

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        data = {cls._QUERY_KEY: str(query), **cls._PARAMS}

        if hasattr(cls, "_LANG_MAP"):
            lang_name = cls._LANG_MAP.get(query.lang, "")
            data[cls._LANG_KEY] = lang_name

        params["url"] = (
            f"{cls._URL}?{urlencode(data)}" if cls._METHOD == "GET" else cls._URL
        )
        params["headers"].update(cls._HEADERS)
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

            results.append(Result(title, httpx.URL(url), text, src))

        return results


class XPathEngine(CstmEngine):
    """Base class for a x-path search engine."""

    _HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    @staticmethod
    def _parse_response(response: httpx.Response) -> html.HtmlElement:
        return etree.fromstring(response.text, parser=html.html_parser)

    @staticmethod
    def _iter(root: html.HtmlElement, path: etree.XPath) -> list[str]:
        return path(root)

    @staticmethod
    def _get(root: html.HtmlElement, path: Optional[etree.XPath]) -> Optional[str]:
        if path is None or not (elems := path(root)):
            return None
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
    _ENGINE: ClassVar[object]
    _MODE: ClassVar[SearchMode] = SearchMode.WEB

    @classmethod
    def _request(cls, query: ParsedQuery, params: dict[str, Any]) -> dict[str, Any]:
        cls._ENGINE.search_type = cls._MODE.value
        return cls._ENGINE.request(str(query), params)

    @classmethod
    def _response(cls, response: httpx.Response) -> list[Result]:
        return [
            Result.from_dict(result)
            for result in cls._ENGINE.response(response)
            if "title" in result and "url" in result
        ]


class Bing(SearxEngine):
    """Search on Bing."""

    WEIGHT = 1.3
    _ENGINE = bing


class BingImages(Bing):
    """Search images on Bing."""

    _ENGINE = bing_images


class Mojeek(XPathEngine):
    """Search on Mojeek."""

    _URL = "https://www.mojeek.com/search"

    _RESULT_PATH = etree.XPath('//a[@class="ob"]')
    _TITLE_PATH = etree.XPath("../h2/a")
    _URL_PATH = etree.XPath("./@href")
    _TEXT_PATH = etree.XPath('../p[@class="s"]')


class MojeekImages(Mojeek):
    """Search images on Mojeek."""

    QUERY_EXTENSIONS = QueryExtensions(0)

    _PARAMS = {"fmt": "images"}

    _RESULT_PATH = etree.XPath('//a[@class="js-img-a"]')
    _TITLE_PATH = etree.XPath("./@data-title")
    _TEXT_PATH = None
    _SRC_PATH = etree.XPath("./img/@src")


class Stract(SearxEngine):
    """Search on stract."""

    # FIXME region selection doesn't really work
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


_MODE_MAP = {
    SearchMode.WEB: {Bing, Mojeek, Stract, Alexandria, RightDao, Yep, SeSe, Google},
    SearchMode.IMAGES: {BingImages, MojeekImages, YepImages},
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
