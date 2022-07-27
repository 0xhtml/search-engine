"""Module to perform a search."""

import atexit
import enum
import re
from typing import Optional

import httpx
import jsonpath_ng
import jsonpath_ng.ext
from lxml import etree, html

from . import sessions
from .asyncio_wrapper import async_run
from .query import ParsedQuery
from .results import Result

_HTTPX_CLIENT = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=10),
    timeout=httpx.Timeout(5, pool=None),
)
atexit.register(async_run, _HTTPX_CLIENT.aclose())


StrMap = dict[str, str]


class Method(enum.Enum):
    """Supported http methods."""

    GET = enum.auto()
    POST = enum.auto()


class Engine:
    """Base class for a search engine."""

    URL: str
    METHOD: Method = Method.GET

    PARAMS: StrMap = {}
    QUERY_KEY: str = "q"

    HEADERS: StrMap = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image"
        "/avif,image/webp,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Android 12; Mobile; rv:101.0) Gecko/101.0 "
        "Firefox/101.0",
    }

    LANG_MAP: StrMap
    LANG_KEY: str

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None):
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    @classmethod
    async def _request_mixin(cls, params: StrMap, headers: StrMap):
        pass

    @classmethod
    async def _make_request(cls, query: ParsedQuery) -> httpx.Response:
        params = {cls.QUERY_KEY: query.query, **cls.PARAMS}
        headers = {**cls.HEADERS}

        if hasattr(cls, "LANG_MAP"):
            lang_name = cls.LANG_MAP.get(query.lang, None)
            if lang_name is not None:
                params[cls.LANG_KEY] = lang_name

        await cls._request_mixin(params, headers)

        if cls.METHOD is Method.GET:
            response = await _HTTPX_CLIENT.get(
                cls.URL, params=params, headers=headers
            )
        elif cls.METHOD is Method.POST:
            response = await _HTTPX_CLIENT.post(
                cls.URL, data=params, headers=headers
            )
        else:
            raise NotImplementedError

        return response

    @classmethod
    async def _parse_response(cls, response: httpx.Response) -> list[Result]:
        raise NotImplementedError

    @classmethod
    async def search(cls, query: ParsedQuery) -> list[Result]:
        """Perform a search and return the results."""
        response = await cls._make_request(query)

        if response.status_code != 200:
            cls._log("Didn't receive status code 200", "Error")
            return []

        return await cls._parse_response(response)


class XPathEngine(Engine):
    """Base class for a x-path search engine."""

    RESULT_PATH: etree.XPath
    TITLE_PATH: etree.XPath
    URL_PATH: etree.XPath
    TEXT_PATH: etree.XPath

    URL_FILTER: re.Pattern

    @classmethod
    def _html_to_string(cls, elem: html.Element) -> str:
        return html.tostring(
            elem, encoding="unicode", method="text", with_tail=False
        ).strip()

    @classmethod
    async def _parse_response(cls, response: httpx.Response) -> list[Result]:
        dom = html.fromstring(response.text)

        results = []

        for result in cls.RESULT_PATH(dom):
            urls = cls.URL_PATH(result)
            if not urls:
                continue

            url = urls[0].attrib.get("href")

            if cls.URL_FILTER.match(url):
                continue

            titles = cls.TITLE_PATH(result)
            if not titles:
                continue

            title = cls._html_to_string(titles[0])

            texts = cls.TEXT_PATH(result)
            if texts:
                text = cls._html_to_string(texts[0])
            else:
                text = ""

            results.append(Result(title, url, text))

        return results


class JSONEngine(Engine):
    """Base class for search engine using JSON."""

    RESULT_PATH: jsonpath_ng.JSONPath
    TITLE_PATH: jsonpath_ng.JSONPath
    URL_PATH: jsonpath_ng.JSONPath
    TEXT_PATH: jsonpath_ng.JSONPath

    @classmethod
    async def _parse_response(cls, response: httpx.Response) -> list[Result]:
        json = response.json()

        results = []

        for result in cls.RESULT_PATH.find(json):
            urls = cls.URL_PATH.find(result)
            if not urls:
                continue

            url = urls[0].value

            titles = cls.TITLE_PATH.find(result)
            if not titles:
                continue

            title = titles[0].value

            texts = cls.TEXT_PATH.find(result)
            if texts:
                text = texts[0].value
            else:
                text = ""

            results.append(Result(title, url, text))

        return results


class Google(XPathEngine):
    """Search on Google using StartPage proxy."""

    URL = "https://www.startpage.com/sp/search"

    PARAMS = {"page": "0", "cat": "web"}
    QUERY_KEY = "query"

    LANG_MAP = {"de": "deutsch", "en": "english"}
    LANG_KEY = "language"

    RESULT_PATH = etree.XPath('//div[@class="w-gl__result__main"]')
    TITLE_PATH = etree.XPath(".//h3[1]")
    URL_PATH = etree.XPath('.//a[@class="w-gl__result-title result-link"]')
    TEXT_PATH = etree.XPath('.//p[@class="w-gl__description"]')
    SC_PATH = etree.XPath('//a[@class="footer-home__logo"]')

    URL_FILTER = re.compile(
        r"^https?://(www\.)?(startpage\.com/do/search\?|google\.[a-z]+/aclk)"
    )

    @classmethod
    async def _request_mixin(cls, params: StrMap, headers: StrMap):
        session_key = "google_sc".encode()

        sessions.lock(sessions.Locks.GOOGLE)

        if sessions.has_expired(session_key):
            cls._log("New session")

            response = await _HTTPX_CLIENT.get(
                "https://www.startpage.com", headers=cls.HEADERS
            )
            dom = html.fromstring(response.text)
            params["sc"] = cls.SC_PATH(dom)[0].get("href")[5:]

            sessions.set(session_key, params["sc"], 60 * 60)  # 1hr
        else:
            params["sc"] = sessions.get(session_key).decode()

        sessions.unlock(sessions.Locks.GOOGLE)

        if "langugage" in params:
            params["lui"] = params["language"]


class DuckDuckGo(XPathEngine):
    """Search on DuckDuckGo directly."""

    URL = "https://lite.duckduckgo.com/lite"
    METHOD = Method.POST

    PARAMS = {"df": ""}

    HEADERS = {
        **Engine.HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    LANG_MAP = {"de": "de-DE", "en": "en-US"}
    LANG_KEY = "kl"

    RESULT_PATH = etree.XPath('//a[@class="result-link"]')
    TITLE_PATH = etree.XPath(".")
    URL_PATH = TITLE_PATH
    TEXT_PATH = etree.XPath("../../following::tr")

    URL_FILTER = re.compile(r"^https?://(help\.)?duckduckgo\.com/")

    @classmethod
    async def _parse_response(cls, response: httpx.Response) -> list[Result]:
        headers = {
            key: value
            for key, value in response.request.headers.items()
            if key in {"user-agent", "accept-encoding", "accept", "cookie"}
        }

        await _HTTPX_CLIENT.get(
            "https://duckduckgo.com/t/sl_l", headers=headers
        )

        return await super()._parse_response(response)


class Qwant(JSONEngine):
    """Search on Qwant supporting de and en only."""

    URL = "https://api.qwant.com/v3/search/web"

    PARAMS = {"count": "10", "offset": "0"}

    LANG_MAP = {"de": "de_DE", "en": "en_US"}
    LANG_KEY = "locale"

    RESULT_PATH = jsonpath_ng.ext.parse(
        "data.result.items.mainline[?(@.type == web)].items[*]"
    )
    TITLE_PATH = jsonpath_ng.parse("title")
    URL_PATH = jsonpath_ng.parse("url")
    TEXT_PATH = jsonpath_ng.parse("desc")


class Alexandria(JSONEngine):
    """Search on alexandria an english only search engine."""

    URL = "https://api.alexandria.org"

    PARAMS = {"a": "1", "c": "a"}

    RESULT_PATH = jsonpath_ng.parse("results[*]")
    TITLE_PATH = jsonpath_ng.parse("title")
    URL_PATH = jsonpath_ng.parse("url")
    TEXT_PATH = jsonpath_ng.parse("snippet")


_LANG_MAP = {
    "*": {Google, DuckDuckGo},
    "de": {Google, DuckDuckGo, Qwant},
    "en": {Google, DuckDuckGo, Qwant, Alexandria},
}


def get_lang_engines(lang: str) -> set[Engine]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get(lang, _LANG_MAP["*"])
