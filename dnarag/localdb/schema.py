"""Helpers for creating the canonical Local Bio-KB schema."""
from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def initialize_schema(db_path: str | Path) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(schema_sql())
    return path
