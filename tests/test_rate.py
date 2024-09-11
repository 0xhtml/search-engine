"""Tests for the rate module."""

import enum

import pytest
from searchengine.engines import Engine
from searchengine.rate import RatedResult
from searchengine.results import AnswerResult, ImageResult, WebResult

RatedResult.__repr__ = (
    lambda self: f"RatedResult(result={self.result}, rating={self.rating})"
)

_WEB = WebResult(None, None, None)
_IMAGE = ImageResult(None, None, None, None)
_ANSWER = AnswerResult(None, None)


class _Cmp(enum.Enum):
    LT = enum.auto()
    GT = enum.auto()
    EQ = enum.auto()


_CMPS = ((0, 0, _Cmp.EQ), (0, 1, _Cmp.GT), (1, 0, _Cmp.LT))


@pytest.mark.parametrize(
    ("a", "b", "cmp"),
    [
        (RatedResult(result, a, Engine), RatedResult(result, b, Engine), cmp)
        for result in (_WEB, _IMAGE, _ANSWER)
        for a, b, cmp in _CMPS
    ]
    + [
        (RatedResult(result, a, Engine), RatedResult(_ANSWER, b, Engine), _Cmp.LT)
        for result in (_WEB, _IMAGE)
        for a, b, _ in _CMPS
    ]
    + [
        (RatedResult(_ANSWER, a, Engine), RatedResult(result, b, Engine), _Cmp.GT)
        for result in (_WEB, _IMAGE)
        for a, b, _ in _CMPS
    ],
)
def test_rated_result_lt(a: RatedResult, b: RatedResult, cmp: _Cmp) -> None:
    """Test the __lt__ method of the RatedResult class."""
    assert not a < a
    assert not b < b
    if cmp == _Cmp.LT:
        assert a < b
        assert not b < a
    elif cmp == _Cmp.GT:
        assert b < a
        assert not a < b
    elif cmp == _Cmp.EQ:
        assert not a < b
        assert not b < a
    else:
        pytest.fail("Invalid comparison")
