"""Module for rating results."""

import asyncio
import heapq
from typing import NamedTuple, Optional, Self

import curl_cffi
import regex

from .common import Search
from .engines import Engine
from .lang import is_lang
from .results import AnswerResult, ImageResult, Result, WebResult
from .snippet import Snippet

PAGE_SIZE = 12

with open("domains.txt") as file:
    _SPAM_DOMAINS = set(file) | {"w3schools.com"}


class RatedResult(NamedTuple):
    """Combined and rated result with a final rating and set of engines associated."""

    result: Result
    rating: float
    engines: frozenset[Engine]
    snippet: Optional[Snippet]

    def result_type(self) -> str:
        """Get the type of the result as a simple string."""
        if isinstance(self.result, WebResult):
            return "web"
        if isinstance(self.result, ImageResult):
            return "image"
        assert isinstance(self.result, AnswerResult)
        return "answer"

    def __lt__(self, other: Self) -> bool:
        """Compare two rated results by rating."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        self_answer = isinstance(self.result, AnswerResult)
        other_answer = isinstance(other.result, AnswerResult)
        if self_answer != other_answer:
            return self_answer < other_answer
        return self.rating < other.rating


class CombinedResult:
    """Combined result with a rating and set of engines associated."""

    def __init__(self, result: Result, rating: float, engine: Engine) -> None:
        """Initialize empty rated result."""
        self.result = result
        self.rating = rating * engine.weight
        self.engines = {engine}
        self.task: Optional[asyncio.Task[Optional[Snippet]]] = None

        self._text = result.text
        if isinstance(result, WebResult | ImageResult):
            self._text += " " + result.title

    def start_loading_snippet(self, session: curl_cffi.AsyncSession) -> None:
        """Start loading snippet asynchronously."""
        if self.task is None:
            self.task = asyncio.create_task(Snippet.load(session, self.result.url))

    def update(self, result: Result, rating: float, engine: Engine) -> bool:
        """Update rated result by combining the result from another engine."""
        assert self.result == result
        max_weight = max(e.weight for e in self.engines)

        if isinstance(self.result, ImageResult) and isinstance(result, WebResult):
            self.result = WebResult(
                self.result.url, self.result.title, self.result.text
            )

        if len(self.result.text) < len(result.text):
            self.result = self.result._replace(text=result.text)

        if engine.weight > max_weight or (
            engine.weight == max_weight
            and len(self.result.url.geturl()) > len(result.url.geturl())
        ):
            self.result = self.result._replace(url=result.url)
        elif result.url.scheme == "https":
            self.result = self.result._replace(
                url=self.result.url._replace(scheme="https")
            )

        if not isinstance(self.result, AnswerResult):
            assert not isinstance(result, AnswerResult)
            if len(self.result.title) < len(result.title):
                self.result = self.result._replace(title=result.title)

        if isinstance(self.result, ImageResult):
            assert isinstance(result, ImageResult)
            if engine.weight > max_weight:
                self.result = self.result._replace(src=result.src)

        if engine not in self.engines:
            self.rating += rating * engine.weight
            self.engines.add(engine)

        assert self._text
        if not isinstance(result, AnswerResult):
            self._text += " " + result.title
        if result.text is not None:
            self._text += " " + result.text

        return True

    def eval(self, lang: str) -> RatedResult:
        """Run additional result evaluation and update rating."""
        if lang != "zh" and regex.search(r"\p{Han}", self._text):
            rating = self.rating * 0.5
        else:
            rating = self.rating * (is_lang(self._text, lang) + 1) / 2

        host = self.result.url.host.removeprefix("www.")
        if host == "reddit.com":
            rating *= 2
        elif host in {"docs.python.org", "stackoverflow.com", "github.com"}:
            rating *= 1.5
        elif host.endswith(".wikipedia.org"):
            rating *= 1.25
        elif host.endswith(".fandom.com") or host in _SPAM_DOMAINS:
            rating *= 0.5

        if self.task is None:
            snippet = None
        elif self.task.done():
            snippet = self.task.result()
        else:
            self.task.cancel()
            snippet = None

        return RatedResult(self.result, rating, frozenset(self.engines), snippet)

    def __lt__(self, other: object) -> bool:
        """Compare two combined results by rating."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        self_rated_result = RatedResult(self.result, self.rating, frozenset(), None)
        other_rated_result = RatedResult(other.result, other.rating, frozenset(), None)
        return self_rated_result < other_rated_result


def _slice_page[T](results: set[T], page: int) -> list[T]:
    return heapq.nlargest(PAGE_SIZE * page, results)[PAGE_SIZE * (page - 1) :]


def combine_engine_results(
    session: curl_cffi.AsyncSession,
    engine: Engine,
    engine_results: list[Result],
    page: int,
    combined_results: set[CombinedResult],
) -> None:
    """Combine results from a single engine into combined_results."""
    for i, result in enumerate(engine_results):
        rating = (1.25**-i) * 10
        for combined_result in combined_results:
            if combined_result.result == result:
                combined_result.update(result, rating, engine)
                break
        else:
            combined_results.add(CombinedResult(result, rating, engine))

    for combined_result in _slice_page(combined_results, page):
        combined_result.start_loading_snippet(session)


def rate_results(results: set[CombinedResult], search: Search) -> list[RatedResult]:
    """Combine results from all engines and rate them."""
    rated_results = {result.eval(search.lang) for result in results}
    return _slice_page(rated_results, search.page)
