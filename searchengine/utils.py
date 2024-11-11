"""Utility functions for the project."""

import asyncio
import contextvars
import functools
import traceback
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


async def timed_wait[K, V](
    tasks: set[asyncio.Task[tuple[V, float]]],
    var: contextvars.ContextVar[K],
    results: dict[K, V],
    exceptions: dict[K, Exception],
    timeout: float | None = None,
) -> float:
    """Wait for tasks to complete and return the maximum time taken by any task."""
    max_time = 0

    if not tasks:
        return max_time
    done, pending = await asyncio.wait(tasks, timeout=timeout)

    for task in done:
        key = task.get_context()[var]
        try:
            result, time = task.result()
            results[key] = result
            max_time = max(time, max_time)
        except Exception as e:
            traceback.print_exc()
            exceptions[key] = e

    for task in pending:
        key = task.get_context()[var]
        task.cancel()
        exceptions[key] = TimeoutError()

    return max_time
