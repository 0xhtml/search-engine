"""Module containing functions to perform a search."""

import asyncio
import math
import traceback
from collections import defaultdict

import aiocache
import curl_cffi

from .common import Search
from .engines import Engine, EngineFeatures, EngineResults, get_engines
from .metrics import metric_errors, metric_success
from .rate import (
    PAGE_SIZE,
    CombinedResult,
    RatedResult,
    combine_engine_results,
    rate_results,
)

MAX_AGE = 60 * 60 * 24


@aiocache.cached(noself=True, ttl=MAX_AGE)
async def _engine_search(
    session: curl_cffi.AsyncSession,
    engine: Engine,
    search: Search,
) -> EngineResults:
    return await engine.search(session, search)


def _max_page(engine: Engine, search: Search) -> int:
    if EngineFeatures.PAGING not in engine.features:
        return 1
    return math.ceil(PAGE_SIZE * search.page / engine.page_size)


async def perform_search(
    session: curl_cffi.AsyncSession,
    search: Search,
) -> tuple[list[RatedResult], dict[Engine, BaseException]]:
    """Perform a search for the given query."""
    engines = get_engines(search)

    results: set[CombinedResult] = set()
    errors: dict[Engine, BaseException] = {}

    tasks = {
        engine: [
            asyncio.create_task(
                _engine_search(session, engine, search._replace(page=page + 1)),
            )
            for page in range(_max_page(engine, search))
        ]
        for engine in engines
    }

    def lookup_task(task: asyncio.Task) -> tuple[Engine, list[asyncio.Task]]:
        for engine, engine_tasks in tasks.items():
            if task in engine_tasks:
                return engine, engine_tasks
        raise RuntimeError

    def find_cut_off(engine_tasks: list[asyncio.Task]) -> int:
        for i, task in enumerate(engine_tasks):
            if task.cancelled() or not task.done() or task.exception() is not None:
                return i
        return len(engine_tasks)

    def callback(task: asyncio.Task) -> None:
        engine, engine_tasks = lookup_task(task)

        if not task.cancelled():
            if (exc := task.exception()) is None:
                metric_success(engine, task.result())
            else:
                traceback.print_exception(exc)
                errors[engine] = exc
                for t in engine_tasks[engine_tasks.index(task) :]:
                    if not t.done():
                        t.cancel()

        cut_off = find_cut_off(engine_tasks)
        if all(t.done() for t in engine_tasks[cut_off:]):
            combine_engine_results(
                session,
                engine,
                [r for t in engine_tasks[:cut_off] for r in t.result().results],
                search.page,
                results,
            )
            for t in engine_tasks:
                t.remove_done_callback(callback)

    for engine_tasks in tasks.values():
        for task in engine_tasks:
            task.add_done_callback(callback)

    prio_tasks = {
        task
        for engine, engine_tasks in tasks.items()
        for task in engine_tasks
        if engine.weight > 1
    }
    await asyncio.wait(prio_tasks)
    completed = {task for task in prio_tasks if task.exception() is None}
    max_time = max(task.result().elapsed for task in completed) if completed else 0
    await asyncio.wait(
        {task for engine_tasks in tasks.values() for task in engine_tasks},
        timeout=max(max_time * 0.5, 1 - max_time),
    )

    for engine, engine_tasks in tasks.items():
        for task in engine_tasks:
            if not task.done():
                task.cancel()
                if engine not in errors:
                    errors[engine] = TimeoutError()

    metric_errors(errors)

    rated_results = rate_results(results, search)

    return rated_results, errors
