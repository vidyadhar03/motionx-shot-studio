"""In-process dispatcher and sweeper (adapted from video-harness `harness/api/generation.py`).

Only schedules work. Ownership is the take lease claimed in SQLite, so the approve path and the
sweeper racing for the same take is harmless: only the claimant does anything.
"""
from __future__ import annotations

import asyncio
import logging

from .generation import GenerationService

log = logging.getLogger("studio.worker")


class Dispatcher:
    def __init__(self, service: GenerationService, *, max_running: int):
        self.service = service
        self._sema = asyncio.Semaphore(max_running)
        self._tasks: set[asyncio.Task] = set()
        self._sweeper: asyncio.Task | None = None

    def schedule(self, take_id: str) -> None:
        task = asyncio.get_running_loop().create_task(self._run(take_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, take_id: str) -> None:
        async with self._sema:
            try:
                await asyncio.to_thread(self.service.run, take_id)
            except Exception:
                log.exception("take %s crashed outside the worker's own handling", take_id)

    async def start(self, sweep_interval_s: float) -> None:
        for tid in await asyncio.to_thread(self.service.recover, startup=True):
            self.schedule(tid)
        self._sweeper = asyncio.get_running_loop().create_task(self._sweep_forever(sweep_interval_s))

    async def _sweep_forever(self, interval_s: float) -> None:
        while True:
            await asyncio.sleep(interval_s)
            try:
                for tid in await asyncio.to_thread(self.service.recover):
                    self.schedule(tid)
            except Exception:
                log.exception("sweep failed; will retry")

    async def stop(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
            try:
                await self._sweeper
            except asyncio.CancelledError:
                pass
        # Worker threads are not cancelled mid-call; their state is durable and recovery resumes it.

    async def drain(self, timeout: float = 30.0) -> None:
        """Test helper: wait for scheduled work to finish."""
        if self._tasks:
            await asyncio.wait(list(self._tasks), timeout=timeout)
