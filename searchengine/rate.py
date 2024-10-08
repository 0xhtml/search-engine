"""Module for rating results."""

import regex
from curl_cffi.requests import get

from .engines import Engine
from .lang import is_lang
from .results import AnswerResult, ImageResult, Result, WebResult
from .url import Url


def _load_domains(url: str) -> set[str]:
    return {
        x.removeprefix("www.")
        for x in get(url).text.splitlines()
        if not x.startswith("#")
    }


MAX_RESULTS = 12
_SPAM_DOMAINS = _load_domains(
    "https://github.com/quenhus/uBlock-Origin-dev-filter/raw/main/dist/other_format/domains/global.txt",
) | _load_domains("https://github.com/rimu/no-qanon/raw/master/domains.txt")


def _comparable_url(url: Url) -> Url:
    assert url.scheme in {"http", "https"}
    return url._replace(
        scheme="http",
        netloc=url.host.removeprefix("www.").replace(
            ".m.wikipedia.org", ".wikipedia.org"
        ),
        path=url.path.replace("%E2%80%93", "-")
        if url.host.endswith(".wikipedia.org")
        else url.path,
        fragment="",
    )


class _InvalidResultTypeError(Exception):
    pass


class RatedResult:
    """Combined result with a rating and set of engines associated."""

    def __init__(self, result: Result, position: int, engine: Engine) -> None:
        """Initialize empty rated result."""
        self.result = result
        self.rating = (MAX_RESULTS - position) * engine.weight
        self.engines = {engine}

    def update(self, result: Result, position: int, engine: Engine) -> bool:
        """Update rated result by combining the result from another engine."""
        if isinstance(result, WebResult) and not isinstance(self.result, WebResult):
            return False
        if isinstance(result, ImageResult) and not isinstance(self.result, ImageResult):
            return False
        if isinstance(result, AnswerResult) or isinstance(self.result, AnswerResult):
            return False
        if _comparable_url(self.result.url) != _comparable_url(result.url):
            return False

        max_weight = max(e.weight for e in self.engines)

        if result.text is not None and (
            self.result.text is None or len(self.result.text) < len(result.text)
        ):
            self.result = self.result._replace(text=result.text)

        if (
            (self.result.url.scheme != "https" and result.url.scheme == "https")
            or engine.weight > max_weight
            or (
                engine.weight == max_weight
                and len(str(self.result.url)) > len(str(result.url))
            )
        ):
            self.result = self.result._replace(url=result.url)

        if len(self.result.title) < len(result.title):
            self.result = self.result._replace(title=result.title)

        if isinstance(self.result, ImageResult):
            assert isinstance(result, ImageResult)
            if self.result.src is None or engine.weight > max_weight:
                self.result = self.result._replace(src=result.src)

        if engine not in self.engines:
            self.rating += (MAX_RESULTS - position) * engine.weight
            self.engines.add(engine)

        return True

    def eval(self, lang: str) -> None:
        """Run additional result evaluation and update rating."""
        if isinstance(self.result, WebResult | ImageResult):
            text = self.result.title
            if self.result.text is not None:
                text += " " + self.result.text
        elif isinstance(self.result, AnswerResult):
            text = self.result.answer
        else:
            raise _InvalidResultTypeError

        if lang != "zh" and regex.search(r"\p{Han}", text):
            self.rating *= 0.5
        else:
            self.rating += 2 * is_lang(text, lang)

        host = self.result.url.host.removeprefix("www.")
        if host == "docs.python.org":
            self.rating *= 1.5
        elif host in {"stackoverflow.com", "reddit.com"}:
            self.rating *= 1.3
        elif host.endswith(".wikipedia.org"):
            self.rating *= 1.1
        elif host in _SPAM_DOMAINS:
            self.rating *= 0.5

    def result_type(self) -> str:
        """Get the type of the result as a simple string."""
        if isinstance(self.result, WebResult):
            return "web"
        if isinstance(self.result, ImageResult):
            return "image"
        if isinstance(self.result, AnswerResult):
            return "answer"
        raise _InvalidResultTypeError

    def __lt__(self, other: "RatedResult") -> bool:
        """Compare two rated results by rating."""
        self_answer = isinstance(self.result, AnswerResult)
        other_answer = isinstance(other.result, AnswerResult)
        if self_answer != other_answer:
            return self_answer < other_answer
        return self.rating < other.rating


def rate_results(
    results: list[tuple[Engine, list[Result]]],
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
