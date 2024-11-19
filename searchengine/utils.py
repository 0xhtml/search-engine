"""Utility functions for the project."""

import asyncio
import functools
from typing import Awaitable, Callable


def timed[**P, R](
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[tuple[R, float]]]:
    """Measure the time taken by async function to execute."""

    @functools.wraps(func)
    async def inner(*args: P.args, **kwargs: P.kwargs) -> tuple[R, float]:
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        result = await func(*args, **kwargs)
        return result, loop.time() - start_time

    return inner
