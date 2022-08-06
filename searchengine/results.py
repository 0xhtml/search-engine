"""Module for results."""

from collections import defaultdict
from typing import NamedTuple

from .lang import detect_lang


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str
    text: str


def order_results(results: list[list[Result]], lang: str) -> list[Result]:
    """Combine results from all engines and order them."""
    max_result_count = max(len(engine_results) for engine_results in results)

    ratings = defaultdict(lambda: 0)
    url_mapped_results = defaultdict(lambda: set())

    for engine_results in results:
        for i, result in enumerate(engine_results):
            ratings[result.url] += max_result_count - i
            url_mapped_results[result.url].add(result)

    rated_results = {
        max(url_mapped_results[url], key=lambda r: len(r.text)): rating
        for url, rating in ratings.items()
    }

    for result in rated_results.keys():
        if detect_lang(f"{result.title} {result.text}") == lang:
            rated_results[result] += 2

    return sorted(
        rated_results, key=rated_results.get, reverse=True  # type: ignore
    )[:10]
