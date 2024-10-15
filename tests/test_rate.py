"""Tests for the rate module."""

import enum

import pytest
from searchengine.engines import Engine
from searchengine.rate import RatedResult
from searchengine.results import AnswerResult, ImageResult, Result, WebResult

RatedResult.__repr__ = (
    lambda self: f"RatedResult(result={self.result}, rating={self.rating})"
)

_WEB = WebResult(None, None, None)
_IMAGE = ImageResult(None, None, None, None)
_ANSWER = AnswerResult(None, None)


class _Engine(Engine):
    def _request(self):
        pass

    def _response(self):
        pass


_ENGINE = _Engine("engine")


class _Cmp(enum.Enum):
    LT = (1, 0)
    GT = (0, 1)
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
