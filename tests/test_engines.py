"""Tests to test the engines."""

import inspect
from typing import Optional

import pytest
import searchengine.engines
from searchengine.engines import Engine
from searchengine.query import ParsedQuery, SearchMode


class _DummyResponse:
    def __init__(self, url: str) -> None:
        self.url = url
        self.status_code = 200


class _DummySession:
    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        data: Optional[str],
        cookies: dict[str, str],
    ) -> _DummyResponse:
        assert method in {"GET", "POST"}
        assert isinstance(url, str)
        assert url
        assert isinstance(headers, dict)
        assert all(isinstance(x, str) for x in headers.keys() | headers.values())
        assert data is None or (isinstance(data, str) and data)
        assert isinstance(cookies, dict)
        assert all(isinstance(x, str) for x in cookies.keys() | cookies.values())
        return _DummyResponse(url)


@pytest.mark.parametrize(
    "engine",
    [
        engine
        for _, engine in inspect.getmembers(searchengine.engines)
        if isinstance(engine, Engine)
    ],
)
@pytest.mark.asyncio
async def test_search(engine: Engine) -> None:
    """Test if the parameters to request get populated."""
    engine._response = lambda _: None  # noqa: SLF001
    query = ParsedQuery(["query"], SearchMode.WEB, 1, "en", None)
    await engine.search(_DummySession(), query)
