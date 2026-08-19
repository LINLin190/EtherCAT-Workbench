from __future__ import annotations

import itertools
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from ..backends.base import EtherCatBackend
from ..models import EtherCatState


class Priority(IntEnum):
    CONTROL = 10
    NORMAL = 20
    WATCH = 50


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    kind: str
    payload: Any


@dataclass(order=True, slots=True)
class _Task:
    priority: int
    sequence: int
    future: Future[Any] = field(compare=False)
    operation: str | Callable[[EtherCatBackend], Any] = field(compare=False)
    args: tuple[Any, ...] = field(compare=False, default=())
    kwargs: dict[str, Any] = field(compare=False, default_factory=dict)


class EtherCatWorker:
    """The sole owner and scheduler of all calls made against one backend/master."""

    def __init__(self, backend_factory: Callable[[], EtherCatBackend]) -> None:
        self._backend_factory = backend_factory
        self._tasks: queue.PriorityQueue[_Task] = queue.PriorityQueue()
        self._events: queue.SimpleQueue[WorkerEvent] = queue.SimpleQueue()
        self._stop = threading.Event()
        self._seq = itertools.count()
        self._thread = threading.Thread(target=self._run, name="EtherCAT Worker", daemon=True)
        self._backend: EtherCatBackend | None = None
        self._cycle_period = 0.0
        self._cycle_timeout_us = 2000
        self._next_cycle = 0.0
        self._max_consecutive_errors = 5
        self._needs_safe_state = False

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def submit(
        self,
        operation: str | Callable[[EtherCatBackend], Any],
        *args: Any,
        priority: Priority = Priority.NORMAL,
        **kwargs: Any,
    ) -> Future[Any]:
        future: Future[Any] = Future()
        self._tasks.put(_Task(int(priority), next(self._seq), future, operation, args, kwargs))
        return future

    def start_cycle(self, period_ms: float, timeout_us: int, max_consecutive_errors: int = 5) -> Future[Any]:
        return self.submit(
            "__start_cycle__", period_ms, timeout_us, max_consecutive_errors, priority=Priority.CONTROL
        )

    def stop_cycle(self) -> Future[Any]:
        return self.submit("__stop_cycle__", priority=Priority.CONTROL)

    def poll_events(self, limit: int = 100) -> list[WorkerEvent]:
        result: list[WorkerEvent] = []
        for _ in range(limit):
            try:
                result.append(self._events.get_nowait())
            except queue.Empty:
                break
        return result

    def shutdown(self, timeout: float = 5.0) -> bool:
        self._stop.set()
        self._tasks.put(_Task(-1, next(self._seq), Future(), "__wake__"))
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @staticmethod
    def _configure_cycle(
        backend: EtherCatBackend, period_ms: float, timeout_us: int, max_consecutive_errors: int
    ) -> tuple[float, int, int, object, object]:
        if period_ms <= 0:
            raise ValueError("Cycle period must be positive")
        backend.map_process_data()
        backend.request_state(None, EtherCatState.SAFE_OP, 2_000_000)
        first_snapshot = backend.exchange_process_data(timeout_us)
        slaves = backend.request_state(None, EtherCatState.OP, 2_000_000)
        return period_ms / 1000.0, timeout_us, max_consecutive_errors, slaves, first_snapshot

    @staticmethod
    def _disable_cycle(backend: EtherCatBackend) -> object:
        return backend.request_state(None, EtherCatState.SAFE_OP, 2_000_000)

    def _execute(self, task: _Task) -> None:
        if task.future.cancelled() or self._backend is None:
            return
        try:
            if task.operation == "__start_cycle__":
                result = self._configure_cycle(self._backend, *task.args, **task.kwargs)
                (
                    self._cycle_period,
                    self._cycle_timeout_us,
                    self._max_consecutive_errors,
                    slaves,
                    first_snapshot,
                ) = result
                self._needs_safe_state = True
                self._next_cycle = time.perf_counter()
                self._events.put(WorkerEvent("process_data", first_snapshot))
                self._events.put(WorkerEvent("cycle_started", slaves))
            elif task.operation == "__stop_cycle__":
                result = self._disable_cycle(self._backend)
                self._cycle_period = 0.0
                self._needs_safe_state = False
                self._events.put(WorkerEvent("cycle_stopped", result))
            elif callable(task.operation):
                result = task.operation(self._backend, *task.args, **task.kwargs)
            elif task.operation == "__wake__":
                result = None
            else:
                result = getattr(self._backend, task.operation)(*task.args, **task.kwargs)
            task.future.set_result(result)
        except BaseException as exc:
            if task.operation == "__start_cycle__" and self._backend.connected:
                self._cycle_period = 0.0
                try:
                    slaves = self._disable_cycle(self._backend)
                    self._needs_safe_state = False
                    self._events.put(WorkerEvent("slaves_changed", slaves))
                except Exception:
                    self._needs_safe_state = True
            task.future.set_exception(exc)
            self._events.put(WorkerEvent("error", exc))

    def _run_cycle(self) -> None:
        assert self._backend is not None
        try:
            snapshot = self._backend.exchange_process_data(self._cycle_timeout_us)
            self._events.put(WorkerEvent("process_data", snapshot))
            if snapshot.consecutive_errors >= self._max_consecutive_errors:
                self._cycle_period = 0.0
                try:
                    slaves = self._disable_cycle(self._backend)
                    self._needs_safe_state = False
                    self._events.put(WorkerEvent("slaves_changed", slaves))
                except Exception:
                    pass
                self._events.put(WorkerEvent("cycle_fault", snapshot))
        except BaseException as exc:
            self._cycle_period = 0.0
            try:
                slaves = self._disable_cycle(self._backend)
                self._needs_safe_state = False
                self._events.put(WorkerEvent("slaves_changed", slaves))
            except Exception:
                pass
            self._events.put(WorkerEvent("cycle_fault", exc))

    def _run(self) -> None:
        self._backend = self._backend_factory()
        self._events.put(WorkerEvent("ready", None))
        try:
            while not self._stop.is_set():
                # A late PDO exchange must never starve stop/control work. Since the
                # queue is priority ordered, a control task (if present) is always first.
                try:
                    control = self._tasks.get_nowait()
                except queue.Empty:
                    control = None
                if control is not None:
                    if control.priority <= int(Priority.CONTROL):
                        self._execute(control)
                        continue
                    self._tasks.put(control)
                now = time.perf_counter()
                if self._cycle_period and now >= self._next_cycle:
                    self._run_cycle()
                    self._next_cycle = max(self._next_cycle + self._cycle_period, time.perf_counter())
                    continue
                timeout = 0.05
                if self._cycle_period:
                    timeout = max(0.0, min(timeout, self._next_cycle - now))
                try:
                    task = self._tasks.get(timeout=timeout)
                except queue.Empty:
                    continue
                self._execute(task)
        finally:
            self._cycle_period = 0.0
            if self._backend.connected:
                try:
                    if self._needs_safe_state:
                        try:
                            self._disable_cycle(self._backend)
                        except Exception as exc:
                            self._events.put(WorkerEvent("error", exc))
                    self._backend.disconnect()
                except Exception as exc:
                    self._events.put(WorkerEvent("error", exc))
            self._events.put(WorkerEvent("stopped", None))
