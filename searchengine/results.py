"""Module for results."""

from typing import NamedTuple

from .lang import detect_lang

_MAX_RESULTS = 12
_ENGINE_WEIGHTS = {"Google": 1.3, "Bing": 1.3}


def _get_engine_weight(engine: str) -> float:
    return _ENGINE_WEIGHTS.get(engine, 1.0)


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str
    text: str


class RatedResult:
    """Combined result with a rating and set of engines associated."""

    result: Result
    rating: float
    engines: set[str]

    def __init__(self, result: Result, position: int, engine: str):
        """Initialize rated result based on result from engine and position."""
        self.result = result
        self.rating = (_MAX_RESULTS - position) * _get_engine_weight(engine)
        self.engines = {engine}

    def update(self, result: Result, position: int, engine: str):
        """Update rated result by combining the result from another engine."""
        if len(result.text) > len(self.result.text):
            self.result = result
        self.rating += (_MAX_RESULTS - position) * _get_engine_weight(engine)
        self.engines.add(engine)

    def eval(self, lang: str):
        """Run additional result evaluation and update rating."""
        if detect_lang(f"{self.result.title} {self.result.text}") == lang:
            self.rating += 2
        if "wikipedia.org" in self.result.url:
            self.rating *= 1.1


def order_results(
    results: list[tuple[str, list[Result]]], lang: str
) -> list[RatedResult]:
    """Combine results from all engines and order them."""
    rated_results: dict[str, RatedResult] = {}

    for engine, engine_results in results:
        for i, result in enumerate(engine_results[:_MAX_RESULTS]):
            if result.url not in rated_results:
                rated_results[result.url] = RatedResult(result, i, engine)
            else:
                rated_results[result.url].update(result, i, engine)

    for result in rated_results.values():
        result.eval(lang)

    return sorted(
        rated_results.values(),
        key=lambda rated_result: rated_result.rating,
        reverse=True,
    )[:_MAX_RESULTS]
