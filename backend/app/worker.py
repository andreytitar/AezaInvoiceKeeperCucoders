"""Точка входа worker: `python -m app.worker`.

Собственный асинхронный цикл с интервалом WORKER_INTERVAL_SECONDS. По SIGTERM дорабатывает
текущую итерацию и выходит.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.container import Container, build_container
from app.infrastructure.logging import setup_logging
from app.models import WorkerHeartbeat

log = logging.getLogger("app.worker")


class Worker:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.stop_event = asyncio.Event()

    async def tick(self) -> None:
        """Одна итерация планировщика. Идемпотентна."""
        ok = True
        try:
            await self._run_jobs()
        except Exception:  # noqa: BLE001
            ok = False
            log.exception("Ошибка в итерации worker")
        self._heartbeat(ok)

    async def _run_jobs(self) -> None:
        pass

    def _heartbeat(self, ok: bool) -> None:
        now = self.c.clock.now()
        with self.c.session_factory() as s:
            stmt = insert(WorkerHeartbeat).values(id=1, last_tick_at=now, last_tick_ok=ok)
            s.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={"last_tick_at": now, "last_tick_ok": ok}))
            s.commit()

    def wait_for_schema(self, timeout: float = 120) -> None:
        import time

        deadline = time.monotonic() + timeout
        while True:
            try:
                with self.c.session_factory() as s:
                    s.execute(text("SELECT 1 FROM worker_heartbeat LIMIT 1"))
                return
            except Exception:  # noqa: BLE001
                if time.monotonic() > deadline:
                    raise
                log.info("Жду готовности схемы БД…")
                time.sleep(2)

    async def run(self) -> None:
        interval = self.c.settings.worker_interval_seconds
        log.info("Worker запущен, интервал %s с", interval)
        while not self.stop_event.is_set():
            await self.tick()
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass
        log.info("Worker остановлен")


async def _main() -> None:
    container = build_container()
    setup_logging(container.settings.log_level)
    worker = Worker(container)
    worker.wait_for_schema()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop_event.set)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
