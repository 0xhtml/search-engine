"""Module for results."""

from collections import defaultdict
from typing import NamedTuple

from .lang import detect_lang


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str

    def __hash__(self) -> int:
        """Hash only the url."""
        return hash(self.url)

    def __eq__(self, other) -> bool:
        """Compare only the url."""
        return self.url == other.url


def order_results(results: list[list[Result]], lang: str) -> list[Result]:
    """Combine results from all engines and order them."""
    max_result_count = max(len(engine_results) for engine_results in results)

    rated_results = defaultdict(lambda: 0)

    for engine_results in results:
        for i, result in enumerate(engine_results):
            rated_results[result] += max_result_count - i

    for result in rated_results.keys():
        if detect_lang(result.title) == lang:
            rated_results[result] += 2

    return sorted(
        rated_results, key=rated_results.get, reverse=True  # type: ignore
    )[:10]
