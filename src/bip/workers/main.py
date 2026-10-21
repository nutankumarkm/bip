"""BIP worker process — ingest, commands, delivery, scheduler."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from bip.core.logging import get_logger, setup_logging
from bip.core.settings import settings

log = get_logger(__name__)


async def run_workers() -> None:
    setup_logging(settings.log_level, settings.log_format)
    log.info("workers_starting")

    stop = asyncio.Event()

    def _signal_handler() -> None:
        log.info("workers_stopping")
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    await stop.wait()
    log.info("workers_stopped")


def main() -> None:
    asyncio.run(run_workers())


if __name__ == "__main__":
    main()
