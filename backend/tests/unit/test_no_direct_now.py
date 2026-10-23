"""Время берётся только из Clock: datetime.now()/date.today()/utcnow() вне domain/clock.py запрещены."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
ALLOWED = {APP / "domain" / "clock.py"}
FORBIDDEN = {"now", "today", "utcnow"}


def test_no_direct_now_calls():
    offenders = []
    for path in APP.rglob("*.py"):
        if path in ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"datetime", "date"}
            ):
                offenders.append(f"{path.relative_to(APP)}:{node.lineno}")
    assert not offenders, f"Используйте Clock вместо прямых вызовов: {offenders}"


def test_domain_has_no_framework_imports():
    banned = ("fastapi", "sqlalchemy", "httpx", "starlette")
    for path in (APP / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert not n.startswith(banned), f"{path.name} импортирует {n}"
