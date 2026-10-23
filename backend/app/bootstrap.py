"""Подготовка при старте api: синхронизация админа из .env и сид (если SEED_ON_START=true)."""

from __future__ import annotations

import logging

from app.container import Container, build_container
from app.infrastructure.logging import setup_logging
from app.services.auth import AuthService

log = logging.getLogger("app.bootstrap")


def bootstrap(container: Container) -> None:
    with container.session_factory() as db:
        AuthService(db, container.clock, container.settings).sync_system_admin()
    if container.settings.app_fake_today:
        log.warning("Включён демо-режим APP_FAKE_TODAY=%s", container.settings.app_fake_today)


def main() -> None:
    container = build_container()
    setup_logging(container.settings.log_level)
    bootstrap(container)
    log.info("Bootstrap завершён")


if __name__ == "__main__":
    main()
