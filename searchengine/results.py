"""Module for results."""

from typing import NamedTuple, Optional

import httpx
import regex

from .engines import Engine, Result
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


class RatedResult:
    """Combined result with a rating and set of engines associated."""

    def __init__(self, result: Result, position: int, engine: type[Engine]) -> None:
        """Initialize empty rated result."""
        self.title = result.title
        self.url = result.url
        self.text = result.text
        self.src = result.src

        self.rating = (_MAX_RESULTS - position) * engine.WEIGHT
        self.engines = {engine}

    def update(self, result: Result, position: int, engine: type[Engine]) -> None:
        """Update rated result by combining the result from another engine."""
        has_higher_weight = engine.WEIGHT > max(e.WEIGHT for e in self.engines)

        if len(self.title) < len(result.title):
            self.title = result.title

        if (
            self.url.scheme != "https" and result.url.scheme == "https"
        ) or has_higher_weight:
            self.url = result.url

        if result.text is not None and (
            self.text is None or len(self.text) < len(result.text)
        ):
            self.text = result.text

        if self.src is None or has_higher_weight:
            self.src = result.src

        if engine not in self.engines:
            self.rating += (_MAX_RESULTS - position) * engine.WEIGHT
            self.engines.add(engine)

    def eval(self, lang: str) -> None:
        """Run additional result evaluation and update rating."""
        text = f"{self.title} {self.text}"
        if lang != "zh" and regex.search(r"\p{Han}", text):
            self.rating *= 0.5
        elif detect_lang(text, lang, None) == lang:
            self.rating += 2

        host = self.url.host.removeprefix("www.")
        if host == "docs.python.org":
            self.rating *= 1.5
        elif host == "stackoverflow.com":
            self.rating *= 1.3
        elif host.endswith(".wikipedia.org"):
            self.rating *= 1.1
        elif host in _SPAM_DOMAINS:
            self.rating *= 0.5


def order_results(
    results: list[tuple[type[Engine], list[Result]]], lang: str
) -> list[RatedResult]:
    """Combine results from all engines and order them."""
    rated_results: dict[httpx.URL, RatedResult] = {}

    for engine, engine_results in results:
        for i, result in enumerate(engine_results[:_MAX_RESULTS]):
            url = result.url.copy_with(
                scheme="http" if result.url.scheme == "https" else result.url.scheme,
                host=result.url.host.removeprefix("www."),
                raw_path=result.url.raw_path.replace(b"%E2%80%93", b"-")
                if result.url.host.endswith(".wikipedia.org")
                else result.url.raw_path,
            )
            if url in rated_results:
                rated_results[url].update(result, i, engine)
            else:
                rated_results[url] = RatedResult(result, i, engine)

    for rated_result in rated_results.values():
        rated_result.eval(lang)

    return sorted(
        rated_results.values(),
        key=lambda rated_result: rated_result.rating,
        reverse=True,
    )[:_MAX_RESULTS]
