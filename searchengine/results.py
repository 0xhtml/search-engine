"""Module for results."""

from typing import NamedTuple, Optional

import httpx

from .lang import detect_lang


def _load_domains(url: str) -> set[str]:
    return {
        x.removeprefix("www.")
        for x in httpx.get(url).text.splitlines()
        if not x.startswith("#")
    }


_MAX_RESULTS = 12
_SPAM_DOMAINS = _load_domains(
    "https://github.com/quenhus/uBlock-Origin-dev-filter/raw/main/dist/other_format/domains/global.txt",
) | _load_domains("https://github.com/rimu/no-qanon/raw/master/domains.txt")


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str
    text: str


class RatedResult:
    """Combined result with a rating and set of engines associated."""

    result: Optional[Result]
    rating: float
    engines: set[type["Engine"]]

    def __init__(self) -> None:
        """Initialize empty rated result."""
        self.result = None
        self.rating = 0
        self.engines = set()

    def update(self, result: Result, position: int, engine: type["Engine"]) -> None:
        """Update rated result by combining the result from another engine."""
        if self.result is None or len(result.text) > len(self.result.text):
            self.result = result
        self.rating += (_MAX_RESULTS - position) * engine.WEIGHT
        self.engines.add(engine)

    def eval(self, lang: str) -> None:
        """Run additional result evaluation and update rating."""
        assert self.result is not None

        if detect_lang(f"{self.result.title} {self.result.text}") == lang:
            self.rating += 2

        host = httpx.URL(self.result.url).host.removeprefix("www.")
        if host == "docs.python.org":
            self.rating *= 1.5
        elif host == "stackoverflow.com":
            self.rating *= 1.3
        elif host.endswith(".wikipedia.org"):
            self.rating *= 1.1
        elif host in _SPAM_DOMAINS:
            self.rating *= 0.6


def order_results(
    results: list[tuple[type["Engine"], list[Result]]], lang: str
) -> list[RatedResult]:
    """Combine results from all engines and order them."""
    rated_results: dict[str, RatedResult] = {}

    for engine, engine_results in results:
        for i, result in enumerate(engine_results[:_MAX_RESULTS]):
            rated_results.setdefault(result.url, RatedResult()).update(
                result, i, engine
            )

    for result in rated_results.values():
        result.eval(lang)

    return sorted(
        rated_results.values(),
        key=lambda rated_result: rated_result.rating,
        reverse=True,
    )[:_MAX_RESULTS]
