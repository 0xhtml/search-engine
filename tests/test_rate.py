"""Tests for the rate module."""

import enum
from urllib.parse import urlparse

import pytest
from searchengine.engines import Engine
from searchengine.rate import RatedResult
from searchengine.results import AnswerResult, ImageResult, Result, WebResult

_URL = urlparse("http://example.com")
_WEB = WebResult(_URL, "", "")
_IMAGE = ImageResult(_URL, "", "", _URL)
_ANSWER = AnswerResult(_URL, "")


_ENGINE = Engine({"name": "", "engine": "google"})
_ENGINE2 = Engine({"name": "", "engine": "google"})


class _Cmp(enum.Enum):
    LT = (0, 1)
    GT = (1, 0)
    EQ = (0, 0)


@pytest.mark.parametrize(
    ("results", "values", "expected"),
    [
        ((result, result), cmp.value, cmp)
        for result in (_WEB, _IMAGE, _ANSWER)
        for cmp in _Cmp
    ]
    + [
        ((result, _ANSWER), cmp.value, _Cmp.LT)
        for result in (_WEB, _IMAGE)
        for cmp in _Cmp
    ],
)
def test_rated_result_lt(
    results: tuple[Result, Result], values: tuple[int, int], expected: _Cmp
) -> None:
    """Test the __lt__ method of the RatedResult class."""
    a = RatedResult(results[0], values[0], _ENGINE)
    b = RatedResult(results[1], values[1], _ENGINE)

    assert not a < a
    assert not b < b

    if expected == _Cmp.LT:
        assert a < b
        assert not b < a
    elif expected == _Cmp.GT:
        assert b < a
        assert not a < b
    elif expected == _Cmp.EQ:
        assert not a < b
        assert not b < a
    else:
        pytest.fail("Invalid comparison")


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
        (_ANSWER, _ANSWER, False),
    ],
)
def test_rated_result_update(a: Result, b: Result, expected: bool) -> None:
    """Test the update method of the RatedResult class."""
    result = RatedResult(a, 1, _ENGINE)
    assert result.update(b, 2, _ENGINE2) == expected
    assert result.rating == (3 if expected else 1)
    assert result.engines == ({_ENGINE, _ENGINE2} if expected else {_ENGINE})
