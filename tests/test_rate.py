"""Tests for the rate module."""

import enum

import pytest
from searchengine.engines import Engine
from searchengine.rate import RatedResult, rate_results
from searchengine.results import Result

from test_results import _ANSWER, _IMAGE, _WEB

_ENGINE = Engine({"name": "", "engine": "google"})


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
    a = RatedResult(results[0], values[0], frozenset({_ENGINE}))
    b = RatedResult(results[1], values[1], frozenset({_ENGINE}))

    assert not a < a
    assert not b < b

    if expected == _Cmp.LT:
        assert a < b
        assert not b < a
    elif expected == _Cmp.GT:
        assert b < a
        assert not a < b
    else:
        assert expected == _Cmp.EQ
        assert not a < b
        assert not b < a


def test_rate_results() -> None:
    """Test the rate results function."""
    rate_results({_ENGINE: [_ANSWER, _IMAGE, _WEB]}, "en")
