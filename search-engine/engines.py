"""Module to perform a search."""

import atexit
import enum
import re
from typing import Optional

import httpx
from lxml import etree, html

from . import sessions
from .query import ParsedQuery
from .results import Result

_HTTPX_CLIENT = httpx.Client(
    limits=httpx.Limits(max_connections=10),
    timeout=httpx.Timeout(2, pool=None),
)
atexit.register(_HTTPX_CLIENT.close)

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

    RESULT_XPATH: etree.XPath
    TITLE_XPATH: etree.XPath
    URL_XPATH: etree.XPath

    URL_FILTER: re.Pattern

    @classmethod
    def _log(cls, msg: str, tag: Optional[str] = None):
        if tag is None:
            print(f"[!] [{cls.__name__}] {msg}")
        else:
            print(f"[!] [{cls.__name__}] [{tag}] {msg}")

    @classmethod
    def _on_request(cls, params: StrMap, headers: StrMap):
        pass

    @classmethod
    def _on_response(cls, response: httpx.Response):
        pass

    @classmethod
    def search(cls, query: ParsedQuery) -> list[Result]:
        """Perform a search and return the results."""
        params = {cls.QUERY_KEY: query.query, **cls.PARAMS}
        headers = {**cls.HEADERS}

        lang_name = cls.LANG_MAP.get(query.lang, None)
        if lang_name is not None:
            params[cls.LANG_KEY] = lang_name

        cls._on_request(params, headers)

        if cls.METHOD is Method.GET:
            response = _HTTPX_CLIENT.get(
                cls.URL, params=params, headers=headers
            )
        elif cls.METHOD is Method.POST:
            response = _HTTPX_CLIENT.post(
                cls.URL, data=params, headers=headers
            )
        else:
            raise NotImplementedError

        cls._on_response(response)

        if response.status_code != 200:
            cls._log("Didn't receive status code 200", "Error")
            return []

        dom = html.fromstring(response.text)

        results = []

        for result in cls.RESULT_XPATH(dom):
            urls = cls.URL_XPATH(result)
            if not urls:
                continue

            url = urls[0].attrib.get("href")

            if cls.URL_FILTER.match(url):
                continue

            titles = cls.TITLE_XPATH(result)
            if not titles:
                continue

            title = titles[0].text

            results.append(Result(title, url))

        return results


class Google(Engine):
    """Search on Google using StartPage proxy."""

    URL = "https://www.startpage.com/sp/search"

    PARAMS = {"page": "0", "cat": "web"}
    QUERY_KEY = "query"

    LANG_MAP = {"de": "deutsch", "en": "english"}
    LANG_KEY = "language"

    RESULT_XPATH = etree.XPath('//div[@class="w-gl__result__main"]')
    TITLE_XPATH = etree.XPath(".//h3[1]")
    URL_XPATH = etree.XPath('.//a[@class="w-gl__result-title result-link"]')
    SC_XPATH = etree.XPath('//a[@class="footer-home__logo"]')

    URL_FILTER = re.compile(
        r"^https?://(www\.)?(startpage\.com/do/search\?|google\.[a-z]+/aclk)"
    )

    @classmethod
    def _on_request(cls, params: StrMap, headers: StrMap):
        session_key = "google_sc".encode()

        sessions.lock(sessions.Locks.GOOGLE)

        if sessions.has_expired(session_key):
            cls._log("New session")

            response = _HTTPX_CLIENT.get(
                "https://www.startpage.com", headers=cls.HEADERS
            )
            dom = html.fromstring(response.text)
            params["sc"] = cls.SC_XPATH(dom)[0].get("href")[5:]

            sessions.set(session_key, params["sc"], 60 * 60)  # 1hr
        else:
            params["sc"] = sessions.get(session_key).decode()

        sessions.unlock(sessions.Locks.GOOGLE)

        if "langugage" in params:
            params["lui"] = params["language"]


class DuckDuckGo(Engine):
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

    RESULT_XPATH = etree.XPath('//a[@class="result-link"]')
    TITLE_XPATH = etree.XPath(".")
    URL_XPATH = TITLE_XPATH

    URL_FILTER = re.compile(r"^https?://(help\.)?duckduckgo\.com/")

    @classmethod
    def _on_response(cls, response: httpx.Response):
        headers = {**response.request.headers}

        del headers["connection"]
        del headers["content-length"]
        del headers["content-type"]
        del headers["host"]

        _HTTPX_CLIENT.get("https://duckduckgo.com/t/sl_l", headers=headers)


class EnglishDummy(Engine):
    """."""

    @classmethod
    def search(cls, query: str) -> list[Result]:
        """."""
        return [Result("ENG LANGUAGE", "http://127.0.0.1:5000")]


_LANG_MAP = {
    "*": (Google, DuckDuckGo),
    "de": (Google, DuckDuckGo),
    "en": (Google, DuckDuckGo, EnglishDummy),
}


def get_lang_engines(lang: str) -> list[Engine]:
    """Return list of enabled engines for the language."""
    return _LANG_MAP.get(lang, _LANG_MAP["*"])
