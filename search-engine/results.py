"""Module for results."""

from collections import defaultdict
from typing import NamedTuple

from . import lang


class Result(NamedTuple):
    """Single result returned by a search."""

    title: str
    url: str


def order_results(
    results: list[list[Result]], query_lang: str
) -> list[Result]:
    """."""
    max_result_count = max(len(engine_results) for engine_results in results)

    rated_results = defaultdict(lambda: 0)

    for engine_results in results:
        for i, result in enumerate(engine_results):
            rated_results[result] += max_result_count - i

    for result in rated_results.keys():
        if lang.detect_lang(result.title) == query_lang:
            rated_results[result] += 2

    return sorted(
        rated_results, key=rated_results.get, reverse=True  # type: ignore
    )
