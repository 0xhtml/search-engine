"""Module to perform a search."""

import json
from typing import ClassVar, Optional, Type, Union

import httpx
import jsonpath_ng
import jsonpath_ng.ext
from lxml import etree, html

from .query import ParsedQuery
from .results import Result


class EngineError(Exception):
    """Exception that is raised when a request fails."""


class Engine:
    """Base class for a search engine."""

    WEIGHT: ClassVar = 1.0

    _URL: ClassVar[str]
    _METHOD: ClassVar[str] = "GET"

    _PARAMS: ClassVar[dict[str, Union[str, bool]]] = {}
    _QUERY_KEY: ClassVar[str] = "q"
    _SIMPLE_QUERY: ClassVar[bool] = False

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
        params = {
            cls._QUERY_KEY: query.to_string(cls._SIMPLE_QUERY),
            **cls._PARAMS,
        }

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
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) "
        "Gecko/20100101 Firefox/112.0",
    }

    _RESULT_PATH: ClassVar[etree.XPath]
    _TITLE_PATH: ClassVar[etree.XPath]
    _URL_PATH: ClassVar[etree.XPath]
    _TEXT_PATH: ClassVar[Optional[etree.XPath]] = None

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

            results.append(Result(title, url, text))

        return results


class JSONEngine(Engine):
    """Base class for search engine using JSON."""

    _RESULT_PATH: ClassVar[jsonpath_ng.JSONPath]
    _TITLE_KEY: ClassVar[str] = "title"
    _URL_KEY: ClassVar[str] = "url"
    _TEXT_KEY: ClassVar[Optional[str]] = None

    @staticmethod
    def _get(root: jsonpath_ng.DatumInContext, key: Optional[str]) -> Optional[str]:
        return None if key is None else root.value.get(key, None)

    @classmethod
    def _parse_response(cls, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in cls._RESULT_PATH.find(json):
            if (url := cls._get(result, cls._URL_KEY)) is None:
                continue

            if (title := cls._get(result, cls._TITLE_KEY)) is None:
                continue

            text = cls._get(result, cls._TEXT_KEY)

            results.append(Result(title, url, text))

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


class Mojeek(XPathEngine):
    """Search on Mojeek."""

    _URL = "https://www.mojeek.com/search"

    _RESULT_PATH = etree.XPath('//a[@class="ob"]')
    _TITLE_PATH = etree.XPath("../h2/a")
    _URL_PATH = etree.XPath("./@href")
    _TEXT_PATH = etree.XPath('../p[@class="s"]')


class Stract(JSONEngine):
    """Search on stract."""

    _URL = "https://stract.com/beta/api/search"
    _METHOD = "POST"

    _PARAMS = {"safeSearch": True}

    _HEADERS = {"Content-Type": "application/json"}

    _QUERY_KEY = "query"
    _SIMPLE_QUERY = True

    _LANG_MAP = {"de": "Germany", "en": "US"}
    _LANG_KEY = "selectedRegion"

    _RESULT_PATH = jsonpath_ng.ext.parse("webpages[*]")
    _TEXT_KEY = "body"


class RightDao(XPathEngine):
    """Search on Right Dao."""

    _URL = "https://rightdao.com/search"

    _RESULT_PATH = etree.XPath('//div[@class="description"]')
    _TITLE_PATH = etree.XPath('../div[@class="title"]')
    _URL_PATH = etree.XPath('../div[@class="title"]/a/@href')
    _TEXT_PATH = etree.XPath(".")


class Alexandria(JSONEngine):
    """Search on Alexandria an English only search engine."""

    _URL = "https://api.alexandria.org"

    _PARAMS = {"a": "1", "c": "a"}
    _SIMPLE_QUERY = True

    _RESULT_PATH = jsonpath_ng.ext.parse("results[*]")
    _TEXT_KEY = "snippet"


class Yep(JSONEngine):
    """Search on Yep."""

    _URL = "https://api.yep.com/fs/2/search"
    _PARAMS = {
        "client": "web",
        "no_correct": "true",
        "safeSearch": "strict",
        "type": "web",
    }
    _SIMPLE_QUERY = True

    _LANG_MAP = {"de": "DE", "en": "US"}
    _LANG_KEY = "gl"

    _RESULT_PATH = jsonpath_ng.ext.parse('[1].results[?type = "Organic"]')
    _TEXT_KEY = "snippet"


_LANG_MAP = {
    "*": {Bing, Mojeek, Yep},
    "de": {Stract},
    "en": {Stract, Alexandria, RightDao},
}


def get_lang_engines(lang: str) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get("*", set()).union(_LANG_MAP.get(lang, set()))
