"""Module containing functions to perform a search."""

import asyncio
import traceback

import aiocache
from curl_cffi.requests import AsyncSession

from .engines import Engine, get_engines
from .metrics import metric_errors, metric_success
from .query import ParsedQuery, SearchMode
from .rate import RatedResult, rate_results
from .results import Result

MAX_AGE = 60 * 60


@aiocache.cached(noself=True, ttl=MAX_AGE)
async def _engine_search(
    session: AsyncSession, engine: Engine, query: ParsedQuery, page: int
) -> tuple[list[Result], float]:
    loop = asyncio.get_running_loop()
    start = loop.time()
    results = await engine.search(session, query, page)
    return results, loop.time() - start


async def perform_search(
    session: AsyncSession, query: ParsedQuery, mode: SearchMode, page: int
) -> tuple[list[RatedResult], dict[Engine, Exception]]:
    """Perform a search for the given query."""
    engines = get_engines(query, mode, page)

    results = {}
    errors = {}

    tasks = {
        asyncio.create_task(_engine_search(session, engine, query, page)): engine
        for engine in engines
    }

    prio_tasks = {task for task, engine in tasks.items() if engine.weight > 1}
    await asyncio.wait(prio_tasks)
    max_time = max(task.result()[1] for task in prio_tasks)

    await asyncio.wait(tasks.keys(), timeout=max(max_time * 0.5, 1 - max_time))
    for task, engine in tasks.items():
        if task.done():
            if (exc := task.exception()) is None:
                engine_results, time = task.result()
                metric_success(engine, len(engine_results), time)
                results[engine] = engine_results
            else:
                traceback.print_exception(exc)
                errors[engine] = exc
        else:
            task.cancel()
            errors[engine] = TimeoutError()

    metric_errors(errors)

    rated_results = rate_results(results, query.lang)

    return rated_results, errors
