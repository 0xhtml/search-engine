"""A small wrapper around asyncio."""

import asyncio
import atexit
from collections.abc import Coroutine
from typing import Any, Union

CoroOrFuture = Union[Coroutine[Any, Any, Any], asyncio.Future[Any]]

_EVENT_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_EVENT_LOOP)


def _cancel_all_tasks(loop):
    to_cancel = asyncio.all_tasks(loop)
    if not to_cancel:
        return

    for task in to_cancel:
        task.cancel()

    loop.run_until_complete(asyncio.gather(*to_cancel, return_exceptions=True))

    for task in to_cancel:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler({
                "message": "unhandled exception during asyncio.run() shutdown",
                "exception": task.exception(),
                "task": task,
            })


@atexit.register
def _shutdown_event_loop():
    try:
        _cancel_all_tasks(_EVENT_LOOP)
        _EVENT_LOOP.run_until_complete(_EVENT_LOOP.shutdown_asyncgens())
        _EVENT_LOOP.run_until_complete(_EVENT_LOOP.shutdown_default_executor())
    finally:
        asyncio.set_event_loop(None)
        _EVENT_LOOP.close()


def async_run(task: CoroOrFuture) -> Any:
    """Call coroutine."""
    return _EVENT_LOOP.run_until_complete(task)


def async_gather(tasks: list[CoroOrFuture]) -> list[Any]:
    """Call asyncio.gather, taking a list of coroutines."""
    return async_run(asyncio.gather(*tasks))
