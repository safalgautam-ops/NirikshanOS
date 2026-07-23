"""Persistent asyncio runtime used by the Flask application."""

from __future__ import annotations

import asyncio
import atexit
import inspect
import threading
from concurrent.futures import Future
from contextvars import copy_context
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from flask import Flask

T = TypeVar("T")


class AsyncRuntime:
    """Own one persistent asyncio loop in a dedicated daemon thread."""

    def __init__(self, *, name: str = "nirikshanos-async") -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=name,
            daemon=True,
        )
        self._started = threading.Event()
        self._closed = False
        self._thread.start()
        self._started.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

        pending = asyncio.all_tasks(self._loop)
        for task in pending:
            task.cancel()
        if pending:
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self._loop.run_until_complete(self._loop.shutdown_asyncgens())
        self._loop.close()

    def run(self, awaitable: Awaitable[T]) -> T:
        """Execute an awaitable on the persistent loop and return its result."""
        if self._closed:
            raise RuntimeError("The application async runtime is closed.")
        if threading.current_thread() is self._thread:
            raise RuntimeError("AsyncRuntime.run() cannot block its own event-loop thread.")

        context = copy_context()
        result: Future[T] = Future()

        def schedule() -> None:
            try:
                task = self._loop.create_task(awaitable, context=context)
            except BaseException as exc:
                result.set_exception(exc)
                return

            def finish(completed: asyncio.Task[T]) -> None:
                try:
                    result.set_result(completed.result())
                except BaseException as exc:
                    result.set_exception(exc)

            task.add_done_callback(finish)

        self._loop.call_soon_threadsafe(schedule, context=context)
        return result.result()

    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


class AsyncFlask(Flask):
    """Flask subclass that runs async views/hooks on one persistent loop."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._async_runtime = AsyncRuntime()
        self._startup_callbacks: list[Callable[[], Any]] = []
        self._shutdown_callbacks: list[Callable[[], Any]] = []
        self._startup_lock = threading.Lock()
        self._startup_complete = False
        self._shutdown_complete = False
        super().__init__(*args, **kwargs)

        self.before_request(self._ensure_started)
        atexit.register(self._shutdown_async_runtime)

    def run_async(self, awaitable: Awaitable[T]) -> T:
        """Run a coroutine on the app's own persistent loop from outside a request - used by service/repository-layer tests (tests/integration) to call async functions directly without a second, conflicting event loop or a duplicate DB pool."""
        self._ensure_started()
        return self._async_runtime.run(awaitable)

    def ensure_sync(self, func: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(func):
            return func

        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return self._async_runtime.run(func(*args, **kwargs))

        return wrapped

    def before_serving(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._startup_callbacks.append(func)
        return func

    def after_serving(self, func: Callable[..., Any]) -> Callable[..., Any]:
        self._shutdown_callbacks.append(func)
        return func

    @staticmethod
    async def _invoke_callbacks(callbacks: list[Callable[[], Any]]) -> None:
        for callback in callbacks:
            value = callback()
            if inspect.isawaitable(value):
                await value

    def _ensure_started(self) -> None:
        if self._startup_complete:
            return
        with self._startup_lock:
            if self._startup_complete:
                return
            self._async_runtime.run(self._invoke_callbacks(self._startup_callbacks))
            self._startup_complete = True

    def _shutdown_async_runtime(self) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        try:
            if self._startup_complete:
                self._async_runtime.run(self._invoke_callbacks(self._shutdown_callbacks))
        finally:
            self._async_runtime.stop()
