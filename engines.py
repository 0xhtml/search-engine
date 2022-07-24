"""Module to perform a search."""

import re
from typing import NamedTuple

import httpx
from lxml import etree, html

import sessions

StrMap = dict[str, str]


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str


class Engine:
    """Base class for a search engine."""

    URL: str
    # METHOD: str = "GET"

    PARAMS: StrMap = {}
    QUERY_KEY: str = "q"

    HEADERS: StrMap = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image"
        "/avif,image/webp,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (Android 12; Mobile; rv:101.0) Gecko/101.0 "
        "Firefox/101.0",
    }

    RESULT_XPATH: etree.XPath
    TITLE_XPATH: etree.XPath
    URL_XPATH: etree.XPath

    URL_FILTER: re.Pattern

    @classmethod
    def _on_request(cls, params: StrMap, headers: StrMap):
        pass

    @classmethod
    def _on_response(cls, response: httpx.Response):
        pass

    @classmethod
    def search(cls, query: str) -> list[Result]:
        """Perform a search and return the results."""
        params = {cls.QUERY_KEY: query, **cls.PARAMS}
        headers = {**cls.HEADERS}

        cls._on_request(params, headers)

        response = httpx.get(cls.URL, params=params, headers=headers)

        cls._on_response(response)

        if response.status_code != 200:
            print("[ERROR] Didn't receive status code 200")
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

    URL = "https://www.startpage.com/do/dsearch"

    PARAMS = {"page": "0", "cat": "web"}
    QUERY_KEY = "query"

    RESULT_XPATH = etree.XPath('//div[@class="w-gl__result__main"]')
    TITLE_XPATH = etree.XPath(".//h3[1]")
    URL_XPATH = etree.XPath('.//a[@class="w-gl__result-title result-link"]')
    SC_XPATH = etree.XPath('//a[@class="footer-home__logo"]')

    URL_FILTER = re.compile(
        r"^https?://(www\.)?(startpage\.com/do/search\?|google\.[a-z]+/aclk)"
    )

    @classmethod
    def _on_request(cls, params: StrMap, headers: StrMap):
        sessions.lock(sessions.Locks.GOOGLE)

        session_key = "google_sc".encode()

        if sessions.has_expired(session_key):
            print("[INFO] New session for google")

            response = httpx.get(
                "https://www.startpage.com", headers=cls.HEADERS
            )
            dom = html.fromstring(response.text)
            params["sc"] = cls.SC_XPATH(dom)[0].get("href")[5:]

            sessions.set(session_key, params["sc"], 60 * 60)  # 1hr
        else:
            params["sc"] = sessions.get(session_key).decode()

        sessions.unlock(sessions.Locks.GOOGLE)


# class DuckDuckGo(Engine):
#     """Search on DuckDuckGo directly."""

#     URL = "https://lite.duckduckgo.com/lite"

#     PARAMS = {"df": ""}

#     RESULT_XPATH = etree.XPath('//a[@class="result-link"]')
#     TITLE_XPATH = etree.XPath(".")
#     URL_XPATH = TITLE_XPATH

#     URL_FILTER = re.compile(r"^https?://(help\.)?duckduckgo\.com/")

#     @classmethod
#     def _on_response(cls, response: httpx.Response, session: Session):
#         headers = {
#                 **response.request.headers
#         }

#         del headers["host"]

#         httpx.get("https://duckduckgo.com/t/sl_l", headers=headers)


class GermanDummy(Engine):
    """."""

    @classmethod
    def search(cls, query: str) -> list[Result]:
        """."""
        return [Result("Sprich Deutsch du *****!", "http://127.0.0.1:5000")]


class EnglishDummy(Engine):
    """."""

    @classmethod
    def search(cls, query: str) -> list[Result]:
        """."""
        return [Result("ENG LANGUAGE", "http://127.0.0.1:5000")]


LANG_MAP = {
    "*": (Google,),
    "de": (Google, GermanDummy),
    "en": (Google, EnglishDummy),
}
