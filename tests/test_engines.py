"""Tests to test the engines."""

import inspect

import pydantic
import pytest
from curl_cffi.requests import AsyncSession

import searchengine.engines
from searchengine.engines import Engine, _Params
from searchengine.query import ParsedQuery

_Params.__pydantic_config__ = pydantic.ConfigDict(  # type: ignore[attr-defined]
    strict=True, str_min_length=1
)
_TYPE_ADAPTER = pydantic.TypeAdapter(_Params)
_QUERY = ParsedQuery(["query"], "en", None)
_SESSION = AsyncSession()


class _ExitEarlyError(Exception):
    pass


@pytest.mark.parametrize(
    "engine",
    [
        engine
        for _, engine in inspect.getmembers(searchengine.engines)
        if isinstance(engine, Engine)
    ],
)
@pytest.mark.asyncio
async def test_request(engine: Engine) -> None:
    """Test if the parameters get populated correctly."""
    super_request = engine._request

    def _request(query: ParsedQuery, params: _Params) -> _Params:
        params = super_request(query, params)
        _TYPE_ADAPTER.validate_python(params)
        assert "url" in params
        raise _ExitEarlyError

    engine._request = _request  # type: ignore[method-assign]

    with pytest.raises(_ExitEarlyError):
        await engine.search(_SESSION, _QUERY, 1)
