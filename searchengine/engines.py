"""Module to perform a search."""

import json
from enum import Enum
from typing import ClassVar, Optional, Type, Union

import httpx
import jsonpath_ng
import jsonpath_ng.ext
from lxml import etree, html

from .query import ParsedQuery, QueryExtensions
from .results import Result


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

    _URL: ClassVar[str]
    _METHOD: ClassVar[str] = "GET"

    _PARAMS: ClassVar[dict[str, Union[str, bool]]] = {}
    _QUERY_KEY: ClassVar[str] = "q"

    _HEADERS: ClassVar[dict[str, str]] = {}

    _LANG_MAP: ClassVar[dict[str, str]]
    _LANG_KEY: ClassVar[str]

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None) -> None:
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    @classmethod
    async def search(
        cls, client: httpx.AsyncClient, query: ParsedQuery
    ) -> list[Result]:
        """Perform a search and return the results."""
        params = {cls._QUERY_KEY: str(query), **cls._PARAMS}

        if hasattr(cls, "_LANG_MAP"):
            lang_name = cls._LANG_MAP.get(query.lang, "")
            params[cls._LANG_KEY] = lang_name

        data = (
            {"data": json.dumps(params)}
            if cls._METHOD == "POST"
            else {"params": params}
        )

        try:
            response = await client.request(
                cls._METHOD, cls._URL, headers=cls._HEADERS, **data
            )
        except httpx.RequestError as e:
            raise EngineError(f"Request error on search ({type(e).__name__})") from e

        if not response.is_success:
            raise EngineError(
                "Didn't receive status code 2xx"
                f" ({response.status_code} {response.reason_phrase})",
            )

        return cls._parse_response(response)


class XPathEngine(Engine):
    """Base class for a x-path search engine."""

    _HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) "
        "Gecko/20100101 Firefox/125.0",
    }

    _RESULT_PATH: ClassVar[etree.XPath]
    _TITLE_PATH: ClassVar[etree.XPath]
    _URL_PATH: ClassVar[etree.XPath]
    _TEXT_PATH: ClassVar[Optional[etree.XPath]] = None
    _SRC_PATH: ClassVar[Optional[etree.XPath]] = None

    @staticmethod
    def _get(root: html.HtmlElement, path: Optional[etree.XPath]) -> Optional[str]:
        if path is None or not (elems := path(root)):
            return None
        if isinstance(elems[0], str):
            return elems[0]
        return html.tostring(
            elems[0], encoding="unicode", method="text", with_tail=False
        )

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> list[Result]:
        dom = etree.fromstring(response.text, parser=html.html_parser)

        results = []

        for result in cls._RESULT_PATH(dom):
            if (url := cls._get(result, cls._URL_PATH)) is None:
                continue

            if (title := cls._get(result, cls._TITLE_PATH)) is None:
                continue

            text = cls._get(result, cls._TEXT_PATH)

            if (src := cls._get(result, cls._SRC_PATH)) is not None:
                src = response.url.join(src)

            results.append(Result(title, httpx.URL(url), text, src))

        return results


class JSONEngine(Engine):
    """Base class for search engine using JSON."""

    _RESULT_PATH: ClassVar[jsonpath_ng.JSONPath]
    _TITLE_PATH: ClassVar[jsonpath_ng.JSONPath] = jsonpath_ng.parse("title")
    _URL_PATH: ClassVar[jsonpath_ng.JSONPath] = jsonpath_ng.parse("url")
    _TEXT_PATH: ClassVar[Optional[jsonpath_ng.JSONPath]] = None
    _SRC_PATH: ClassVar[Optional[jsonpath_ng.JSONPath]] = None

    @staticmethod
    def _get(
        root: jsonpath_ng.DatumInContext, path: Optional[jsonpath_ng.JSONPath]
    ) -> Optional[str]:
        if path is None or not (elems := path.find(root.value)):
            return None
        return elems[0].value

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in cls._RESULT_PATH.find(json):
            if (url := cls._get(result, cls._URL_PATH)) is None:
                continue

            if (title := cls._get(result, cls._TITLE_PATH)) is None:
                continue

            if text := cls._get(result, cls._TEXT_PATH):
                text = html.tostring(
                    etree.fromstring(text, html.html_parser),
                    encoding="unicode",
                    method="text",
                    with_tail=False,
                )

            src = cls._get(result, cls._SRC_PATH)

            results.append(Result(title, httpx.URL(url), text, src))

        return results


class Bing(XPathEngine):
    """Search on Bing using StartPage proxy."""

    WEIGHT = 1.3

    _URL = "https://www.startpage.com/do/dsearch"

    _PARAMS = {"cat": "web", "pl": "ext-ff", "extVersion": "1.1.7"}
    _QUERY_KEY = "query"

    _LANG_MAP = {"de": "deutsch", "en": "english"}
    _LANG_KEY = "language"

    _RESULT_PATH = etree.XPath('//div[starts-with(@class,"result")]')
    _TITLE_PATH = etree.XPath("./a/h2")
    _URL_PATH = etree.XPath("./a/@href")
    _TEXT_PATH = etree.XPath("./p")


class BingImages(JSONEngine, Bing):
    """Search images on Bing using StartPage proxy."""

    _PARAMS = {**Bing._PARAMS, "cat": "pics"}

    _RESULT_PATH = jsonpath_ng.ext.parse(
        'render.presenter.regions.mainline[?display_type="images-bing"].results[*]'
    )
    _URL_PATH = jsonpath_ng.parse("displayUrl")
    _SRC_PATH = jsonpath_ng.parse("rawImageUrl")

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> list[Result]:
        response._content = (
            response.text.split("React.createElement(UIStartpage.AppSerp, ", 1)[1]
            .splitlines()[0]
            .rsplit(")", 1)[0]
        )
        return super()._parse_response(response)


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


class Stract(JSONEngine):
    """Search on stract."""

    # FIXME region selection doesn't really work
    SUPPORTED_LANGUAGES = {"en"}
    QUERY_EXTENSIONS = QueryExtensions.QUOTES | QueryExtensions.SITE

    _URL = "https://stract.com/beta/api/search"
    _METHOD = "POST"

    _PARAMS = {"safeSearch": True}

    _QUERY_KEY = "query"

    _HEADERS = {"Content-Type": "application/json"}

    _RESULT_PATH = jsonpath_ng.ext.parse("webpages[*]")
    _TEXT_PATH = jsonpath_ng.parse("body")


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
    _TEXT_PATH = jsonpath_ng.parse("snippet")


class Yep(JSONEngine):
    """Search on Yep."""

    _URL = "https://api.yep.com/fs/2/search"
    _PARAMS = {
        "client": "web",
        "no_correct": "true",
        "safeSearch": "strict",
        "type": "web",
    }

    _HEADERS = {
        **XPathEngine._HEADERS,
        "Accept": "*/*",
        "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
        "Referer": "https://yep.com/",
        "Origin": "https://yep.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    _LANG_MAP = {"de": "DE", "en": "US"}
    _LANG_KEY = "gl"

    _RESULT_PATH = jsonpath_ng.ext.parse('[1].results[?type="Organic"]')
    _TEXT_PATH = jsonpath_ng.parse("snippet")


class YepImages(Yep):
    """Search images on Yep."""

    QUERY_EXTENSIONS = QueryExtensions(0)

    _PARAMS = {**Yep._PARAMS, "type": "images"}

    _RESULT_PATH = jsonpath_ng.ext.parse('[1].results[?type="Image"]')
    _URL_PATH = jsonpath_ng.parse("host_page")
    _TEXT_PATH = None
    _SRC_PATH = jsonpath_ng.parse("src")


class SeSe(JSONEngine):
    """Search on SeSe."""

    _URL = "https://se-proxy.azurewebsites.net/api/search"

    _PARAMS = {"slice": "0:12"}

    _RESULT_PATH = jsonpath_ng.ext.parse("'结果'[*]")
    _URL_PATH = jsonpath_ng.parse("'网址'")
    _TITLE_PATH = jsonpath_ng.parse("'信息'.'标题'")
    _TEXT_PATH = jsonpath_ng.parse("'信息'.'描述'")


_MODE_MAP = {
    SearchMode.WEB: {Bing, Mojeek, Stract, Alexandria, RightDao, Yep, SeSe},
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
