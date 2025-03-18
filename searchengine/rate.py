"""Module for rating results."""

import heapq
from typing import NamedTuple, Self

import regex

from .engines import Engine
from .lang import is_lang
from .results import AnswerResult, ImageResult, Result, WebResult

with open("domains.txt") as file:
    _SPAM_DOMAINS = set(file)


class RatedResult(NamedTuple):
    """Combined and rated result with a final rating and set of engines associated."""

    result: Result
    rating: float
    engines: frozenset[Engine]

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

        self._text = result.text
        if isinstance(result, WebResult | ImageResult):
            self._text += " " + result.title

    def update(self, result: Result, rating: float, engine: Engine) -> bool:
        """Update rated result by combining the result from another engine."""
        assert self.result == result
        max_weight = max(e.weight for e in self.engines)

        if isinstance(self.result, ImageResult) and isinstance(result, WebResult):
            self.result = WebResult(
                self.result.url, self.result.title, self.result.text
            )

        if len(self.result.text or "") < len(result.text or ""):
            self.result = self.result._replace(text=result.text)

        if result.url.scheme == "https" and self.result.url.scheme != "https":
            self.result = self.result._replace(
                url=self.result.url._replace(scheme="https")
            )

        if engine.weight > max_weight or (
            engine.weight == max_weight
            and len(self.result.url.geturl()) > len(result.url.geturl())
        ):
            self.result = self.result._replace(url=result.url)

        if len(self.result.title) < len(result.title):
            self.result = self.result._replace(title=result.title)

        if isinstance(self.result, ImageResult):
            assert isinstance(result, ImageResult)
            if self.result.src is None or engine.weight > max_weight:
                self.result = self.result._replace(src=result.src)

        if engine not in self.engines:
            self.rating += rating * engine.weight
            self.engines.add(engine)

        assert self._text
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

        host = self.result.url.netloc.removeprefix("www.")
        if host == "reddit.com":
            rating *= 2
        elif host in {"docs.python.org", "stackoverflow.com", "github.com"}:
            rating *= 1.5
        elif host.endswith(".wikipedia.org"):
            rating *= 1.25
        elif host in _SPAM_DOMAINS:
            rating *= 0.5

        return RatedResult(self.result, rating, frozenset(self.engines))


def combine_results(results: dict[Engine, list[Result]]) -> set[CombinedResult]:
    """Combine results from all engines."""
    combined_results = set()

    for engine, result_list in results.items():
        for i, result in enumerate(result_list):
            rating = (1.25**-i) * 10
            for combined_result in combined_results:
                if combined_result.result == result:
                    combined_result.update(result, rating, engine)
                    break
            else:
                combined_results.add(CombinedResult(result, rating, engine))

    return combined_results


def rate_results(results: dict[Engine, list[Result]], lang: str) -> list[RatedResult]:
    """Combine results from all engines and rate them."""
    rated_results = {result.eval(lang) for result in combine_results(results)}
    return heapq.nlargest(12, rated_results)
