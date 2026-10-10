"""Bounded, priority-ordered execution of tasks.

The old runner backgrounded ~60 `vol` processes at once per image (and several images at once),
which thrashed RAM/CPU. Here at most `workers` tasks run at a time, core tables first.
"""

from __future__ import annotations

import heapq
import itertools
import logging
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable, Iterable

from .models import TaskResult, TaskStatus, utcnow
from .tasks import RunContext, Task

log = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self, workers: int, on_result: Callable[[TaskResult], None], stop_event: threading.Event | None = None):
        self.workers = max(1, workers)
        self.on_result = on_result
        self.stop_event = stop_event or threading.Event()
        self._sequence = itertools.count()

    def run(self, tasks: Iterable[Task], ctx: RunContext) -> list[TaskResult]:
        queue: list[tuple[int, int, Task]] = []
        for task in tasks:
            self._push(queue, task)

        results: list[TaskResult] = []
        running: dict[Future, Task] = {}
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="vol") as pool:
            while queue or running:
                while queue and len(running) < self.workers and not self.stop_event.is_set():
                    _, _, task = heapq.heappop(queue)
                    log.info("start %s", task)
                    running[pool.submit(task.run, ctx)] = task
                if not running:
                    break  # stop requested and nothing in flight
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    task = running.pop(future)
                    result = self._result_of(future, task)
                    log.info("done  %s: %s in %.0fs", task, result.status.value, result.duration_seconds)
                    results.append(result)
                    for followup in result.followups:
                        self._push(queue, followup)
                    self.on_result(result)

        for _, _, task in queue:  # only non-empty if a stop was requested
            results.append(TaskResult.skipped(task.name, task.table, "shutdown requested"))
        return results

    def _push(self, queue: list, task: Task) -> None:
        heapq.heappush(queue, (int(task.tier), next(self._sequence), task))

    @staticmethod
    def _result_of(future: Future, task: Task) -> TaskResult:
        try:
            return future.result()
        except Exception as exc:  # a bug in a task must not kill the whole image
            log.exception("task %s crashed", task)
            now = utcnow()
            return TaskResult(task.name, task.table, TaskStatus.FAILED, now, now, error=f"{type(exc).__name__}: {exc}")
