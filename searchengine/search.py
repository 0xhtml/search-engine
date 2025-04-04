"""Module containing functions to perform a search."""

import asyncio
import traceback

import aiocache
import curl_cffi

from .common import Search
from .engines import Engine, get_engines
from .metrics import metric_errors, metric_success
from .rate import RatedResult, rate_results, CombinedResult, combine_engine_results
from .results import Result

MAX_AGE = 60 * 60 * 24


@aiocache.cached(noself=True, ttl=MAX_AGE)
async def _engine_search(
    session: curl_cffi.AsyncSession, engine: Engine, search: Search
) -> tuple[list[Result], float]:
    loop = asyncio.get_running_loop()
    start = loop.time()
    results = await engine.search(session, search)
    return results, loop.time() - start


async def perform_search(
    session: curl_cffi.AsyncSession, search: Search
) -> tuple[list[RatedResult], dict[Engine, BaseException]]:
    """Perform a search for the given query."""
    engines = get_engines(search)

    results: set[CombinedResult] = set()
    errors: dict[Engine, BaseException] = {}

    tasks = {
        asyncio.create_task(_engine_search(session, engine, search)): engine
        for engine in engines
    }

    def callback(task: asyncio.Task) -> None:
        engine = tasks[task]
        if (exc := task.exception()) is None:
            engine_results, time = task.result()
            metric_success(engine, len(engine_results), time)
            combine_engine_results(session, engine, engine_results, results)
        else:
            traceback.print_exception(exc)
            errors[engine] = exc

    for task in tasks:
        task.add_done_callback(callback)

    prio_tasks = {task for task, engine in tasks.items() if engine.weight > 1}
    await asyncio.wait(prio_tasks)
    completed = {task for task in prio_tasks if task.exception() is None}
    max_time = max(task.result()[1] for task in completed) if completed else 0

    await asyncio.wait(tasks.keys(), timeout=max(max_time * 0.5, 1 - max_time))

    for task, engine in tasks.items():
        if not task.done():
            task.remove_done_callback(callback)
            task.cancel()
            errors[engine] = TimeoutError()

    metric_errors(errors)

    rated_results = rate_results(results, search.lang)

    return rated_results, errors
