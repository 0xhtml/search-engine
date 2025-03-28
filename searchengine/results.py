"""Module containing the Result types."""

from html import unescape
from typing import NamedTuple, Optional, Self

import searx.result_types

from .url import URL


def _parse_url(result: dict) -> URL:
    assert "url" in result
    assert isinstance(result["url"], str)
    assert result["url"]
    return URL.parse(result["url"])


def _parse_title(result: dict) -> str:
    assert "title" in result
    assert isinstance(result["title"], str)
    assert result["title"]
    return result["title"]


def _parse_content(result: dict) -> str:
    if "content" not in result:
        return ""
    assert isinstance(result["content"], str)
    if result["content"] == result.get("title"):
        return ""
    return result["content"]


class WebResult(NamedTuple):
    """An image result consisting of title, url, text and src."""

    url: URL
    title: str
    text: str

    @classmethod
    def from_searx(cls, result: dict) -> Self:
        """Parse a web result from a dict returned by searx."""
        return cls(_parse_url(result), _parse_title(result), _parse_content(result))

    def __eq__(self, other: object) -> bool:
        """Check if two results are equal based on URL."""
        return _result_url_eq(self, other)


class ImageResult(NamedTuple):
    """An image result consisting of title, url, text and src."""

    url: URL
    title: str
    text: str
    src: URL

    @classmethod
    def from_searx(cls, result: dict) -> Self:
        """Parse an image result from a dict returned by searx."""
        assert "img_src" in result
        assert isinstance(result["img_src"], str)
        assert result["img_src"]
        assert "thumbnail_src" not in result or isinstance(result["thumbnail_src"], str)
        assert "thumbnail_src" not in result or result["thumbnail_src"]
        assert "template" in result
        assert result["template"] == "images.html"
        return cls(
            _parse_url(result),
            _parse_title(result),
            _parse_content(result),
            URL.parse(unescape(result.get("thumbnail_src", result["img_src"]))),
        )

    def __eq__(self, other: object) -> bool:
        """Check if two results are equal based on URL."""
        return _result_url_eq(self, other)


class AnswerResult(NamedTuple):
    """An answer result consisting of answer and url."""

    url: URL
    text: str

    @classmethod
    def from_searx(cls, result: searx.result_types.Answer) -> Self:
        """Parse an answer result from a searx Answer."""
        assert result.url is not None
        assert result.url
        assert result.answer
        return cls(URL.parse(result.url), result.answer)


type Result = WebResult | ImageResult | AnswerResult


def _result_url_eq(self: WebResult | ImageResult, other: object) -> bool:
    if not isinstance(other, WebResult) and not isinstance(other, ImageResult):
        return False
    return self.url == other.url


def result_from_searx(result: dict | searx.result_types.Answer) -> Optional[Result]:
    """Parse a result from a dict or Answer returned by searx."""
    if isinstance(result, searx.result_types.Answer):
        return AnswerResult.from_searx(result)

    if (
        "suggestion" in result
        or "correction" in result
        or "infobox" in result
        or "number_of_results" in result
        or "engine_data" in result
    ):
        return None

    if "img_src" in result:
        return ImageResult.from_searx(result)

    return WebResult.from_searx(result)
