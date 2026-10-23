"""Генерация openapi/openapi.yml из кода: `python -m app.openapi_dump [путь]` (make openapi)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "openapi" / "openapi.yml"


def render() -> str:
    os.environ.setdefault("SECRET_KEY", "openapi-dump-placeholder")
    os.environ.setdefault("ADMIN_PASSWORD", "openapi-dump-placeholder")
    from app.main import create_app

    schema = create_app().openapi()
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=120)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("OPENAPI_PATH", DEFAULT_PATH))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8")
    print(f"OpenAPI записан в {target}")


if __name__ == "__main__":
    main()
