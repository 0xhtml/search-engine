"""Module to perform a search."""

import enum
import re
from typing import Optional, Type

import httpx
import jsonpath_ng
import jsonpath_ng.ext
from lxml import etree, html

from . import sessions
from .query import ParsedQuery
from .results import Result

StrMap = dict[str, str]


class Method(enum.Enum):
    """Supported http methods."""

    GET = enum.auto()
    POST = enum.auto()


class Engine:
    """Base class for a search engine."""

    _URL: str
    _METHOD: Method = Method.GET

    _PARAMS: StrMap = {}
    _QUERY_KEY: str = "q"

    _HEADERS: StrMap = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image"
        "/avif,image/webp,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Android 12; Mobile; rv:101.0) Gecko/101.0 "
        "Firefox/101.0",
    }

    _LANG_MAP: StrMap
    _LANG_KEY: str

    def __init__(self, client: httpx.AsyncClient):
        """Initialize engine."""
        self._client = client

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None):
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    async def _request_mixin(self, params: StrMap, headers: StrMap):
        pass

    async def _make_request(self, query: ParsedQuery) -> httpx.Response:
        params = {self._QUERY_KEY: query.query, **self._PARAMS}
        headers = {**self._HEADERS}

        if hasattr(self, "LANG_MAP"):
            lang_name = self._LANG_MAP.get(query.lang, None)
            if lang_name is not None:
                params[self._LANG_KEY] = lang_name

        await self._request_mixin(params, headers)

        if self._METHOD is Method.GET:
            response = await self._client.get(
                self._URL, params=params, headers=headers
            )
        elif self._METHOD is Method.POST:
            response = await self._client.post(
                self._URL, data=params, headers=headers
            )
        else:
            raise NotImplementedError

        return response

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    async def search(self, query: ParsedQuery) -> list[Result]:
        """Perform a search and return the results."""
        response = await self._make_request(query)

        if response.status_code != 200:
            self._log("Didn't receive status code 200", "Error")
            return []

        return await self._parse_response(response)


class XPathEngine(Engine):
    """Base class for a x-path search engine."""

    _RESULT_PATH: etree.XPath
    _TITLE_PATH: etree.XPath
    _URL_PATH: etree.XPath
    _TEXT_PATH: etree.XPath

    _URL_FILTER: re.Pattern

    @staticmethod
    def _html_to_string(elem: html.Element) -> str:
        return html.tostring(
            elem, encoding="unicode", method="text", with_tail=False
        ).strip()

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        dom = html.fromstring(response.text)

        results = []

        for result in self._RESULT_PATH(dom):
            urls = self._URL_PATH(result)
            if not urls:
                continue

            url = urls[0].attrib.get("href")

            if self._URL_FILTER.match(url):
                continue

            titles = self._TITLE_PATH(result)
            if not titles:
                continue

            title = self._html_to_string(titles[0])

            texts = self._TEXT_PATH(result)
            if texts:
                text = self._html_to_string(texts[0])
            else:
                text = ""

            results.append(Result(title, url, text))

        return results


class JSONEngine(Engine):
    """Base class for search engine using JSON."""

    _RESULT_PATH: jsonpath_ng.JSONPath
    _TITLE_PATH: jsonpath_ng.JSONPath
    _URL_PATH: jsonpath_ng.JSONPath
    _TEXT_PATH: jsonpath_ng.JSONPath

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in self._RESULT_PATH.find(json):
            urls = self._URL_PATH.find(result)
            if not urls:
                continue

            url = urls[0].value

            titles = self._TITLE_PATH.find(result)
            if not titles:
                continue

            title = titles[0].value

            texts = self._TEXT_PATH.find(result)
            if texts:
                text = texts[0].value
            else:
                text = ""

            results.append(Result(title, url, text))

        return results


class Google(XPathEngine):
    """Search on Google using StartPage proxy."""

    _URL = "https://www.startpage.com/sp/search"

    _PARAMS = {"page": "0", "cat": "web"}
    _QUERY_KEY = "query"

    _LANG_MAP = {"de": "deutsch", "en": "english"}
    _LANG_KEY = "language"

    _RESULT_PATH = etree.XPath('//div[@class="w-gl__result__main"]')
    _TITLE_PATH = etree.XPath(".//h3[1]")
    _URL_PATH = etree.XPath('.//a[@class="w-gl__result-title result-link"]')
    _TEXT_PATH = etree.XPath('.//p[@class="w-gl__description"]')
    _SC_PATH = etree.XPath('//a[@class="footer-home__logo"]')

    _URL_FILTER = re.compile(
        r"^https?://(www\.)?(startpage\.com/do/search\?|google\.[a-z]+/aclk)"
    )

    async def _request_mixin(self, params: StrMap, headers: StrMap):
        session_key = "google_sc".encode()

        sessions.lock(sessions.Locks.GOOGLE)

        if sessions.has_expired(session_key):
            self._log("New session")

            response = await self._client.get(
                "https://www.startpage.com", headers=self._HEADERS
            )
            dom = html.fromstring(response.text)
            params["sc"] = self._SC_PATH(dom)[0].get("href")[5:]

            sessions.set(session_key, params["sc"], 60 * 60)  # 1hr
        else:
            params["sc"] = sessions.get(session_key).decode()

        sessions.unlock(sessions.Locks.GOOGLE)

        if "langugage" in params:
            params["lui"] = params["language"]


class DuckDuckGo(XPathEngine):
    """Search on DuckDuckGo directly."""

    _URL = "https://lite.duckduckgo.com/lite"
    _METHOD = Method.POST

    _PARAMS = {"df": ""}

    _HEADERS = {
        **Engine._HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    _LANG_MAP = {"de": "de-DE", "en": "en-US"}
    _LANG_KEY = "kl"

    _RESULT_PATH = etree.XPath('//a[@class="result-link"]')
    _TITLE_PATH = etree.XPath(".")
    _URL_PATH = _TITLE_PATH
    _TEXT_PATH = etree.XPath("../../following::tr")

    _URL_FILTER = re.compile(r"^https?://(help\.)?duckduckgo\.com/")

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        headers = {
            key: value
            for key, value in response.request.headers.items()
            if key in {"user-agent", "accept-encoding", "accept", "cookie"}
        }

        # TODO: check if headers=self._HEADERS would be fine
        await self._client.get(
            "https://duckduckgo.com/t/sl_l", headers=headers
        )

        return await super()._parse_response(response)


class Qwant(JSONEngine):
    """Search on Qwant supporting de and en only."""

    _URL = "https://api.qwant.com/v3/search/web"

    _PARAMS = {"count": "10", "offset": "0"}

    _LANG_MAP = {"de": "de_DE", "en": "en_US"}
    _LANG_KEY = "locale"

    _RESULT_PATH = jsonpath_ng.ext.parse(
        "data.result.items.mainline[?(@.type == web)].items[*]"
    )
    _TITLE_PATH = jsonpath_ng.parse("title")
    _URL_PATH = jsonpath_ng.parse("url")
    _TEXT_PATH = jsonpath_ng.parse("desc")


class Alexandria(JSONEngine):
    """Search on alexandria an english only search engine."""

    _URL = "https://api.alexandria.org"

    _PARAMS = {"a": "1", "c": "a"}

    _RESULT_PATH = jsonpath_ng.parse("results[*]")
    _TITLE_PATH = jsonpath_ng.parse("title")
    _URL_PATH = jsonpath_ng.parse("url")
    _TEXT_PATH = jsonpath_ng.parse("snippet")


_LANG_MAP = {
    "*": {Google, DuckDuckGo},
    "de": {Google, DuckDuckGo, Qwant},
    "en": {Google, DuckDuckGo, Qwant, Alexandria},
}


def get_lang_engines(lang: str) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get(lang, _LANG_MAP["*"])
