"""Module to perform a search."""

import json
from typing import Optional, Type, Union

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

    _URL: str
    _METHOD: str = "GET"

    _PARAMS: dict[str, Union[str, bool]] = {}
    _QUERY_KEY: str = "q"
    _SIMPLE_QUERY: bool = False

    _HEADERS: dict[str, str] = {}

    _LANG_MAP: dict[str, str]
    _LANG_KEY: str

    @staticmethod
    def normalize(text: str, sep: str = " ") -> str:
        """Normalize text."""
        return sep.join(text.splitlines()).strip()

    def __init__(self, client: httpx.AsyncClient):
        """Initialize engine."""
        self._client = client

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None):
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    async def search(self, query: ParsedQuery) -> list[Result]:
        """Perform a search and return the results."""
        params = {
            self._QUERY_KEY: query.to_string(self._SIMPLE_QUERY),
            **self._PARAMS,
        }
        headers = {**self._HEADERS}

        if hasattr(self, "_LANG_MAP"):
            lang_name = self._LANG_MAP.get(query.lang, "")
            params[self._LANG_KEY] = lang_name

        data = (
            {"data": json.dumps(params)}
            if self._METHOD == "POST"
            else {"params": params}
        )

        try:
            response = await self._client.request(
                self._METHOD,
                self._URL,
                headers=headers,
                **data,  # type: ignore
            )
        except httpx.RequestError as e:
            raise EngineError(f"Request error on search ({type(e).__name__})")

        if not response.is_success:
            raise EngineError(
                "Didn't receive status code 2xx"
                f" ({response.status_code} {response.reason_phrase})"
            )

        return await self._parse_response(response)


class XPathEngine(Engine):
    """Base class for a x-path search engine."""

    _HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) "
        "Gecko/20100101 Firefox/112.0",
    }

    _RESULT_PATH: etree.XPath
    _TITLE_PATH: Optional[etree.XPath]
    _URL_PATH: Optional[etree.XPath]
    _TEXT_PATH: Optional[etree.XPath]

    @staticmethod
    def _html_to_string(elem: html.Element) -> str:
        return html.tostring(
            elem, encoding="unicode", method="text", with_tail=False
        )

    @staticmethod
    def _get_elem(
        root: html.Element, path: Optional[etree.XPath]
    ) -> Optional[html.Element]:
        if path is None:
            return root

        elems = path(root)
        if not elems:
            return None

        return elems[0]

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        dom = etree.fromstring(response.text, parser=html.html_parser)

        results = []

        for result in self._RESULT_PATH(dom):
            url = self._get_elem(result, self._URL_PATH)
            if url is None:
                continue
            url = self.normalize(url.attrib.get("href"), "")

            title = self._get_elem(result, self._TITLE_PATH)
            if title is None:
                continue
            title = self.normalize(self._html_to_string(title))

            if (
                not hasattr(self, "_TEXT_PATH")
                or (text := self._get_elem(result, self._TEXT_PATH)) is None
            ):
                text = ""
            else:
                text = self.normalize(self._html_to_string(text))

            results.append(Result(title, url, text))

        return results


class JSONEngine(Engine):
    """Base class for search engine using JSON."""

    _RESULT_PATH: jsonpath_ng.JSONPath
    _TITLE_KEY: str = "title"
    _URL_KEY: str = "url"
    _TEXT_KEY: str = "snippet"

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in self._RESULT_PATH.find(json):
            url = self.normalize(result.value.get(self._URL_KEY, ""), "")
            if not url:
                continue

            title = self.normalize(result.value.get(self._TITLE_KEY, ""))
            if not title:
                continue

            text = self.normalize(result.value.get(self._TEXT_KEY, ""))

            results.append(Result(title, url, text))

        return results


class Google(XPathEngine):
    """Search on Google using StartPage proxy."""

    _URL = "https://www.startpage.com/do/dsearch"

    _PARAMS = {"cat": "web", "pl": "ext-ff", "extVersion": "1.3.0"}
    _QUERY_KEY = "query"

    _LANG_MAP = {"de": "deutsch", "en": "english"}
    _LANG_KEY = "language"

    _RESULT_PATH = etree.XPath('//div[@class="w-gl__result__main"]')
    _TITLE_PATH = etree.XPath("./div/a/h3")
    _URL_PATH = etree.XPath('./div/a[@class="w-gl__result-url result-link"]')
    _TEXT_PATH = etree.XPath("./p")


class Bing(JSONEngine):
    """Search on Bing using the API."""

    _URL = "https://api.bing.microsoft.com/v7.0/search"

    _HEADERS = {
        "Ocp-Apim-Subscription-Key": "API-KEY",
        **JSONEngine._HEADERS,
    }

    _LANG_MAP = {"de": "de-DE", "en": "en-US"}
    _LANG_KEY = "mkt"

    _RESULT_PATH = jsonpath_ng.ext.parse("webPages.value[*]")
    _TITLE_KEY = "name"


class Mojeek(XPathEngine):
    """Search on Mojeek."""

    _URL = "https://www.mojeek.com/search"

    _RESULT_PATH = etree.XPath('//a[@class="ob"]')
    _TITLE_PATH = etree.XPath("../h2/a")
    _URL_PATH = None
    _TEXT_PATH = etree.XPath('../p[@class="s"]')


class Stract(JSONEngine):
    """Search on stract."""

    _URL = "https://trystract.com/beta/api/search"
    _METHOD = "POST"

    _PARAMS = {"safeSearch": True}

    _HEADERS = {
        **JSONEngine._HEADERS,
        "Content-Type": "application/json",
    }

    _QUERY_KEY = "query"
    _SIMPLE_QUERY = True

    _LANG_MAP = {"de": "Germany", "en": "US"}
    _LANG_KEY = "selectedRegion"

    _RESULT_PATH = jsonpath_ng.ext.parse("webpages[*]")
    _TEXT_KEY = "body"


class RightDao(XPathEngine):
    """Search on Right Dao."""

    _URL = "https://rightdao.com/search"

    _RESULT_PATH = etree.XPath('//div[@class="item"]/div[@class="description"]')
    _TITLE_PATH = etree.XPath('../div[@class="title"]/a')
    _URL_PATH = _TITLE_PATH
    _TEXT_PATH = None


class Alexandria(JSONEngine):
    """Search on Alexandria an English only search engine."""

    _URL = "https://api.alexandria.org"

    _PARAMS = {"a": "1", "c": "a"}
    _SIMPLE_QUERY = True

    _RESULT_PATH = jsonpath_ng.ext.parse("results[*]")


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


_LANG_MAP = {
    "*": {Google, Bing, Mojeek, Yep},
    "de": {Stract},
    "en": {Stract, Alexandria, RightDao},
}


def get_lang_engines(lang: str) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get("*", set()).union(_LANG_MAP.get(lang, set()))
