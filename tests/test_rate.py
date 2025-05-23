"""Tests for the rate module."""

import enum

import pytest
from searchengine.engines import Engine
from searchengine.rate import CombinedResult, RatedResult
from searchengine.results import Result

from test_results import _ANSWER, _IMAGE, _WEB


class _Cmp(enum.Enum):
    LT = (0, 1)
    GT = (1, 0)
    EQ = (0, 0)


_ENGINE = Engine({"name": "", "engine": "google"}, page_size=10)
_CMPS = [
    ((result, result), cmp.value, cmp)
    for result in (_WEB, _IMAGE, _ANSWER)
    for cmp in _Cmp
] + [
    ((result, _ANSWER), cmp.value, _Cmp.LT) for result in (_WEB, _IMAGE) for cmp in _Cmp
]


@pytest.mark.parametrize(("results", "values", "expected"), _CMPS)
def test_combined_result_lt(
    results: tuple[Result, Result],
    values: tuple[int, int],
    expected: _Cmp,
) -> None:
    """Test the __lt__ method of the CombinedResult class."""
    a = CombinedResult(results[0], values[0], _ENGINE)
    b = CombinedResult(results[1], values[1], _ENGINE)

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


@pytest.mark.parametrize(("results", "values", "expected"), _CMPS)
def test_rated_result_lt(
    results: tuple[Result, Result],
    values: tuple[int, int],
    expected: _Cmp,
) -> None:
    """Test the __lt__ method of the RatedResult class."""
    a = RatedResult(results[0], values[0], frozenset(), None)
    b = RatedResult(results[1], values[1], frozenset(), None)

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
