"""Подготовка при старте api: синхронизация админа из .env и сид (если SEED_ON_START=true)."""

from __future__ import annotations

import logging

from app.container import build_container
from app.infrastructure.logging import setup_logging

log = logging.getLogger("app.bootstrap")


def main() -> None:
    container = build_container()
    setup_logging(container.settings.log_level)
    log.info("Bootstrap завершён")


if __name__ == "__main__":
    main()
