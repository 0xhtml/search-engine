"""Module to perform a search."""

from . import importer  # isort: skip

import inspect
import json
import sys
from abc import ABC, abstractmethod
from enum import Flag, auto
from html import unescape
from types import ModuleType
from typing import Literal, Optional, TypedDict
from urllib.parse import urlencode, urljoin

import jsonpath_ng
import jsonpath_ng.ext
import searx
import searx.data
import searx.enginelib
import searx.engines
from curl_cffi.requests import AsyncSession, Response
from curl_cffi.requests.session import HttpMethod
from lxml import etree, html

from .query import ParsedQuery, SearchMode
from .results import AnswerResult, ImageResult, Result, WebResult
from .url import Url


class _RequiredParams(TypedDict):
    cookies: dict[str, str]
    data: Optional[str]
    headers: dict[str, str]
    language: str
    method: HttpMethod
    pageno: int
    safesearch: Literal[0, 1, 2]
    searxng_locale: str
    time_range: Optional[str]


class _Params(_RequiredParams, total=False):
    url: str


class _Features(Flag):
    PAGING = auto()
    QUOTES = auto()
    SITE = auto()

    @classmethod
    def required(cls, query: ParsedQuery, page: int) -> "_Features":
        extensions = cls(0)

        if page != 1:
            extensions |= cls.PAGING

        if any(" " in word for word in query.words):
            extensions |= cls.QUOTES

        if query.site is not None:
            extensions |= cls.SITE

        return extensions


class StatusCodeError(Exception):
    """Exception that is raised if a request to an engine doesn't return 2xx."""

    def __init__(self, response: Response) -> None:
        """Initialize the exception w/ an Response object."""
        super().__init__(f"{response.status_code} {response.reason}")


_DEFAULT_FEATURES = _Features(0)


class Engine(ABC):
    """Base class for a search engine."""

    def __init__(
        self,
        name: str,
        *,
        mode: SearchMode = SearchMode.WEB,
        weight: float = 1.0,
        features: _Features = _DEFAULT_FEATURES,
        method: HttpMethod = "GET",
    ) -> None:
        """Initialize engine."""
        self._name = name
        self.mode = mode
        self.weight = weight
        self.features = features
        self._method = method

    def _log(self, msg: str, tag: Optional[str] = None) -> None:
        if tag is None:
            print(f"[!] [{self}] {msg}")
        else:
            print(f"[!] [{self}] [{tag}] {msg}")

    @abstractmethod
    def _request(self, query: ParsedQuery, params: _Params) -> _Params:
        pass

    @abstractmethod
    def _response(self, response: Response) -> list[Result]:
        pass

    def supports_language(self, language: str) -> bool:
        """Check if the engine supports a query language."""
        return True

    async def search(
        self,
        session: AsyncSession,
        query: ParsedQuery,
        page: int,
    ) -> list[Result]:
        """Perform a search and return the results."""
        params = self._request(
            query,
            _Params(
                cookies={},
                data=None,
                headers={},
                language=query.lang,
                method=self._method,
                pageno=page,
                safesearch=2,
                searxng_locale=query.lang,
                time_range=None,
            ),
        )

        response = await session.request(
            params["method"],
            params["url"],
            headers=params["headers"],
            data=params["data"],
            cookies=params["cookies"],
        )

        if not (200 <= response.status_code < 300):
            raise StatusCodeError(response)

        response.search_params = params
        response.url = Url.parse(response.url)
        return self._response(response)

    def __str__(self) -> str:
        """Return name of engine in PascalCase."""
        return self._name.title().replace(" ", "")


_DEFAULT_PARAMS: dict[str, str] = {}


class _CstmEngine[Path, Element](Engine):
    def __init__(
        self,
        name: str,
        *,
        mode: SearchMode = SearchMode.WEB,
        weight: float = 1.0,
        features: _Features = _DEFAULT_FEATURES,
        method: HttpMethod = "GET",
        url: str,
        query_key: str = "q",
        params: dict[str, str] = _DEFAULT_PARAMS,
        result_path: Path,
        title_path: Path,
        url_path: Path,
        text_path: Path,
        src_path: Optional[Path] = None,
    ) -> None:
        if mode == SearchMode.IMAGES and src_path is None:
            msg = "src_path is required for image search"
            raise ValueError(msg)

        self._url = url
        self._query_key = query_key
        self._params = params
        self._result_path = result_path
        self._title_path = title_path
        self._url_path = url_path
        self._text_path = text_path
        self._src_path = src_path

        super().__init__(
            name,
            mode=mode,
            weight=weight,
            features=features,
            method=method,
        )

    @staticmethod
    @abstractmethod
    def _parse_response(response: Response) -> Element:
        pass

    @staticmethod
    @abstractmethod
    def _iter(root: Element, path: Path) -> list[Element]:
        pass

    @staticmethod
    @abstractmethod
    def _get(root: Element, path: Optional[Path]) -> str:
        pass

    def _request(self, query: ParsedQuery, params: _Params) -> _Params:
        data = {self._query_key: str(query), **self._params}

        if self._method == "GET":
            params["url"] = f"{self._url}?{urlencode(data)}"
        elif self._method == "POST":
            params["url"] = self._url
            params["data"] = json.dumps(data)
        else:
            msg = f"Unsupported method {self._method}"
            raise ValueError(msg)

        return params

    def _response(self, response: Response) -> list[Result]:
        root = self._parse_response(response)

        results: list[Result] = []

        for result in self._iter(root, self._result_path):
            title = self._get(result, self._title_path)
            assert title

            _url = self._get(result, self._url_path)
            assert _url
            url = Url.parse(urljoin(str(response.url), _url))

            text = self._get(result, self._text_path)

            if self.mode == SearchMode.IMAGES:
                src = self._get(result, self._src_path)
                assert src
                results.append(ImageResult(title, url, text, Url.parse(src)))
                continue

            results.append(WebResult(title, url, text))

        return results


class _XPathEngine(_CstmEngine[etree.XPath, html.HtmlElement]):
    @staticmethod
    def _parse_response(response: Response) -> html.HtmlElement:
        return html.document_fromstring(response.text)

    @staticmethod
    def _iter(root: html.HtmlElement, path: etree.XPath) -> list[html.HtmlElement]:
        return path(root)

    @staticmethod
    def _get(root: html.HtmlElement, path: Optional[etree.XPath]) -> str:
        if path is None or not (elems := path(root)):
            return ""
        if isinstance(elems[0], str):
            return elems[0]
        return html.tostring(
            elems[0],
            encoding="unicode",
            method="text",
            with_tail=False,
        )


class _JSONEngine(_CstmEngine[jsonpath_ng.JSONPath, jsonpath_ng.DatumInContext]):
    @staticmethod
    def _parse_response(response: Response) -> jsonpath_ng.DatumInContext:
        return jsonpath_ng.Root().find(response.json())

    @staticmethod
    def _iter(
        root: jsonpath_ng.DatumInContext, path: jsonpath_ng.JSONPath
    ) -> list[jsonpath_ng.DatumInContext]:
        return path.find(root)

    @staticmethod
    def _get(
        root: jsonpath_ng.DatumInContext, path: Optional[jsonpath_ng.JSONPath]
    ) -> str:
        if path is None or not (elems := path.find(root)):
            return ""
        return elems[0].value


class _SearxEngine(Engine):
    def __init__(
        self,
        name: str,
        *,
        mode: Optional[SearchMode] = None,
        weight: float = 1.0,
        features: _Features = _DEFAULT_FEATURES,
        method: HttpMethod = "GET",
    ) -> None:
        for engine in searx.settings["engines"]:
            if engine["name"] == name:
                _engine = searx.engines.load_engine(engine)
                assert isinstance(_engine, ModuleType)
                self._engine = _engine
                break
        else:
            msg = f"Searx engine {name} not found"
            raise ValueError(msg)

        if mode is None:
            for _mode in SearchMode:
                if _mode.searx_category() in self._engine.categories:
                    mode = _mode
                    break
            else:
                msg = f"Failed to detect mode for {name}"
                raise ValueError(msg)
        else:
            self._engine.search_type = mode.value  # type: ignore[attr-defined]

        if self._engine.paging:
            features |= _Features.PAGING

        super().__init__(
            name,
            mode=mode,
            weight=weight,
            features=features,
            method=method,
        )

    def _request(self, query: ParsedQuery, params: _Params) -> _Params:
        return self._engine.request(str(query), params)  # type: ignore[no-any-return]

    def _response(self, response: Response) -> list[Result]:
        if not response.text:
            return []

        results: list[Result] = []

        for result in self._engine.response(response):
            if "number_of_results" in result or "suggestion" in result:
                continue

            assert "url" in result
            assert isinstance(result["url"], str)
            if not result["url"]:
                self._log(f"result w/o URL {result}")
                continue

            url = Url.parse(result["url"])

            if "answer" in result:
                assert isinstance(result["answer"], str)
                assert result["answer"]
                results.append(AnswerResult(result["answer"], url))
                continue

            assert "title" in result
            assert isinstance(result["title"], str)
            if not result["title"]:
                self._log(f"result w/o title {result}")
                continue

            if "img_src" in result:
                src = result.get("thumbnail_src", result["img_src"])
                assert isinstance(src, str)
                assert src
                assert result.get("template") == "images.html"
                results.append(
                    ImageResult(
                        result["title"],
                        url,
                        result.get("content", ""),
                        Url.parse(unescape(src)),
                    )
                )
                continue

            assert "content" in result
            assert isinstance(result["content"], str)
            results.append(
                WebResult(
                    result["title"],
                    url,
                    result["content"],
                )
            )

        return results

    def supports_language(self, language: str) -> bool:
        if not self._engine.language_support:
            return super().supports_language(language)
        assert isinstance(self._engine.traits, searx.enginelib.traits.EngineTraits)
        return self._engine.traits.is_locale_supported(language)


_ALEXANDRIA = _JSONEngine(
    "alexandria",
    features=_Features.SITE,
    url="https://api.alexandria.org",
    params={"a": "1", "c": "a"},
    result_path=jsonpath_ng.parse("results[*]"),
    title_path=jsonpath_ng.parse("title"),
    url_path=jsonpath_ng.parse("url"),
    text_path=jsonpath_ng.parse("snippet"),
)
# TODO: check if bing does support quotation
_BING = _SearxEngine("bing", weight=1.3, features=_Features.SITE)
_BING_IMAGES = _SearxEngine("bing images", weight=1.3, features=_Features.SITE)
_GOOGLE = _SearxEngine("google", weight=1.3, features=_Features.QUOTES | _Features.SITE)
_GOOGLE_IMAGES = _SearxEngine(
    "google images", weight=1.3, features=_Features.QUOTES | _Features.SITE
)
_GOOGLE_SCHOLAR = _SearxEngine("google scholar", weight=1.3)
_MOJEEK = _SearxEngine("mojeek", features=_Features.SITE)
_REDDIT = _SearxEngine("reddit", weight=0.7, mode=SearchMode.WEB)
_RIGHT_DAO = _SearxEngine("right dao", features=_Features.QUOTES | _Features.SITE)
_SESE = _JSONEngine(
    "sese",
    features=_Features.SITE,
    url="https://se-proxy.azurewebsites.net/api/search",
    params={"slice": "0:12"},
    result_path=jsonpath_ng.ext.parse("'结果'[?'信息'.'标题' != '']"),
    url_path=jsonpath_ng.parse("'网址'"),
    title_path=jsonpath_ng.parse("'信息'.'标题'"),
    text_path=jsonpath_ng.parse("'信息'.'描述'"),
)
_STRACT = _SearxEngine("stract", features=_Features.QUOTES | _Features.SITE)
_YEP = _SearxEngine("yep", features=_Features.SITE)
_YEP_IMAGES = _SearxEngine("yep", mode=SearchMode.IMAGES, features=_Features.SITE)


def get_engines(query: ParsedQuery, mode: SearchMode, page: int) -> set[Engine]:
    """Return list of enabled engines for the language."""
    return {
        engine
        for _, engine in inspect.getmembers(sys.modules[__name__])
        if isinstance(engine, Engine)
        if engine.mode == mode
        if engine.supports_language(query.lang)
        if _Features.required(query, page) in engine.features
    }
