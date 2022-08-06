"""Module to perform a search."""

from typing import Optional, Type

import httpx
import jsonpath_ng
import jsonpath_ng.ext
from lxml import etree, html

from . import sessions
from .query import ParsedQuery
from .results import Result

StrMap = dict[str, str]


class Engine:
    """Base class for a search engine."""

    _URL: str
    _METHOD: str = "GET"

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

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    async def search(self, query: ParsedQuery) -> list[Result]:
        """Perform a search and return the results."""
        params = {self._QUERY_KEY: query.query, **self._PARAMS}
        headers = {**self._HEADERS}

        if hasattr(self, "_LANG_MAP"):
            lang_name = self._LANG_MAP.get(query.lang, None)
            if lang_name is not None:
                params[self._LANG_KEY] = lang_name

        await self._request_mixin(params, headers)

        response = await self._client.request(
            self._METHOD,
            self._URL,
            **{"data" if self._METHOD == "POST" else "params": params},
            headers=headers,
        )

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

    @staticmethod
    def _html_to_string(elem: html.Element) -> str:
        return html.tostring(
            elem, encoding="unicode", method="text", with_tail=False
        ).strip()

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        dom = etree.fromstring(response.text, parser=html.html_parser)

        results = []

        for result in self._RESULT_PATH(dom):
            urls = self._URL_PATH(result)
            if not urls:
                continue

            url = urls[0].attrib.get("href")

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
    _TITLE_KEY: str = "title"
    _URL_KEY: str = "url"
    _TEXT_KEY: str

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in self._RESULT_PATH.find(json):
            url = result.value.get(self._URL_KEY, "")
            if not url:
                continue

            title = result.value.get(self._TITLE_KEY, "")
            if not title:
                continue

            text = result.value.get(self._TEXT_KEY, "")

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
    _TITLE_PATH = etree.XPath("./div/a/h3")
    _URL_PATH = etree.XPath('./div/a[@class="w-gl__result-title result-link"]')
    _TEXT_PATH = etree.XPath('./p[@class="w-gl__description"]')
    _SC_PATH = etree.XPath('//a[@class="footer-home__logo"]')

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
    _METHOD = "POST"

    _PARAMS = {"df": ""}

    _HEADERS = {
        **XPathEngine._HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    _LANG_MAP = {"de": "de-DE", "en": "en-US"}
    _LANG_KEY = "kl"

    _RESULT_PATH = etree.XPath('//tr[not(@class)]/td/a[@class="result-link"]')
    _TITLE_PATH = etree.XPath(".")
    _URL_PATH = _TITLE_PATH
    _TEXT_PATH = etree.XPath("../../following::tr")

    async def _parse_response(self, response: httpx.Response) -> list[Result]:
        await self._client.get(
            "https://duckduckgo.com/t/sl_l", headers=super()._HEADERS
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
    _TEXT_KEY = "desc"


class Alexandria(JSONEngine):
    """Search on alexandria an english only search engine."""

    _URL = "https://api.alexandria.org"

    _PARAMS = {"a": "1", "c": "a"}

    _RESULT_PATH = jsonpath_ng.parse("results[*]")
    _TEXT_KEY = "snippet"


_LANG_MAP = {
    "*": {Google, DuckDuckGo},
    "de": {Google, DuckDuckGo, Qwant},
    "en": {Google, DuckDuckGo, Qwant, Alexandria},
}


def get_lang_engines(lang: str) -> set[Type[Engine]]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get(lang, _LANG_MAP["*"])
