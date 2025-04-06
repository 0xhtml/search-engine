"""Tests for the result types."""

import pytest
import searx.result_types
from searchengine.results import (AnswerResult, ImageResult, Result, WebResult,
                                  result_from_searx)
from searchengine.url import URL

_URL = URL.parse("http://example.com/")
_WEB = WebResult(_URL, "web: title", "web: text")
_IMAGE = ImageResult(_URL, "image: title", "image: text", _URL)
_ANSWER = AnswerResult(_URL, "answer: text")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (_WEB, _WEB, True),
        (_WEB, _IMAGE, True),
        (_WEB, _ANSWER, False),
        (_IMAGE, _WEB, True),
        (_IMAGE, _IMAGE, True),
        (_IMAGE, _ANSWER, False),
        (_ANSWER, _WEB, False),
        (_ANSWER, _IMAGE, False),
        (_ANSWER, _ANSWER, True),
        (_ANSWER, AnswerResult(_URL, "a"), False),
    ],
)
def test_result_eq(a: Result, b: Result, expected: bool) -> None:
    """Test the __eq__ method of the different result classes."""
    assert (a == b) == expected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {
                "url": _WEB.url.geturl(),
                "title": _WEB.title,
                "content": _WEB.text,
            },
            _WEB,
        ),
        (
            {
                "url": _IMAGE.url.geturl(),
                "title": _IMAGE.title,
                "content": _IMAGE.text,
                "img_src": _IMAGE.src.geturl(),
                "template": "images.html",
            },
            _IMAGE,
        ),
        (
            searx.result_types.Answer(answer=_ANSWER.text, url=_ANSWER.url.geturl()),
            _ANSWER,
        ),
    ],
)
def test_result_from_searx(result: dict, expected: Result) -> None:
    """Test the result_from_searx function."""
    parsed = result_from_searx(result)
    assert parsed is not None
    assert type(parsed) is type(expected)
    assert tuple(parsed) == tuple(expected)
