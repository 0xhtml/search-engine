"""Module for rating results."""

import httpx
import regex

from .engines import Engine
from .lang import is_lang
from .results import Result


def _load_domains(url: str) -> set[str]:
    return {
        x.removeprefix("www.")
        for x in httpx.get(url).text.splitlines()
        if not x.startswith("#")
    }


MAX_RESULTS = 12
_SPAM_DOMAINS = _load_domains(
    "https://github.com/quenhus/uBlock-Origin-dev-filter/raw/main/dist/other_format/domains/global.txt",
) | _load_domains("https://github.com/rimu/no-qanon/raw/master/domains.txt")


def _comparable_url(url: httpx.URL) -> httpx.URL:
    assert url.scheme in {"http", "https"}
    return url.copy_with(
        scheme="http",
        host=url.host.removeprefix("www.").replace(
            ".m.wikipedia.org", ".wikipedia.org"
        ),
        raw_path=url.raw_path.replace(b"%E2%80%93", b"-")
        if url.host.endswith(".wikipedia.org")
        else url.raw_path,
    )


class _InvalidResultTypeError(Exception):
    pass


class RatedResult:
    """Combined result with a rating and set of engines associated."""

    def __init__(self, result: Result, position: int, engine: type[Engine]) -> None:
        """Initialize empty rated result."""
        self.title = result.title
        self.url = result.url
        self.text = result.text
        self.src = result.src

        self.rating = (MAX_RESULTS - position) * engine.WEIGHT
        self.engines = {engine}

    def update(self, result: Result, position: int, engine: type[Engine]) -> bool:
        """Update rated result by combining the result from another engine."""
        if _comparable_url(self.url) != _comparable_url(result.url):
            return False

        max_weight = max(e.WEIGHT for e in self.engines)

        if len(self.title) < len(result.title):
            self.title = result.title

        if (
            (self.url.scheme != "https" and result.url.scheme == "https")
            or engine.WEIGHT > max_weight
            or (
                engine.WEIGHT == max_weight
                and len(str(self.url)) > len(str(result.url))
            )
        ):
            self.url = result.url

        if result.text is not None and (
            self.text is None or len(self.text) < len(result.text)
        ):
            self.text = result.text

        if self.src is None or engine.WEIGHT > max_weight:
            self.src = result.src

        if engine not in self.engines:
            self.rating += (MAX_RESULTS - position) * engine.WEIGHT
            self.engines.add(engine)

        return True

    def eval(self, lang: str) -> None:
        """Run additional result evaluation and update rating."""
        text = f"{self.title} {self.text or ''}"

        if lang != "zh" and regex.search(r"\p{Han}", text):
            self.rating *= 0.5
        else:
            self.rating += 2 * is_lang(text, lang)

        host = self.url.host.removeprefix("www.")
        if host == "docs.python.org":
            self.rating *= 1.5
        elif host in {"stackoverflow.com", "reddit.com"}:
            self.rating *= 1.3
        elif host.endswith(".wikipedia.org"):
            self.rating *= 1.1
        elif host in _SPAM_DOMAINS:
            self.rating *= 0.5

    def __lt__(self, other: "RatedResult") -> bool:
        """Compare two rated results by rating."""
        return self.rating < other.rating


def rate_results(
    results: list[tuple[type[Engine], list[Result]]],
    lang: str,
) -> set[RatedResult]:
    """Combine results from all engines and rate them."""
    rated_results: set[RatedResult] = set()

    for engine, engine_results in results:
        for i, result in enumerate(engine_results[:MAX_RESULTS]):
            for rated_result in rated_results:
                if rated_result.update(result, i, engine):
                    break
            else:
                rated_results.add(RatedResult(result, i, engine))

    for rated_result in rated_results:
        rated_result.eval(lang)

    return rated_results
