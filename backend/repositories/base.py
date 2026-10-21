"""repo 层公共工具"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

# 统一从 core 引,避免各 repo 各自 import 一堆
from core.database import (  # noqa: F401
    cursor, execute, executemany, fetch_all, fetch_one, fetch_value, insert, transaction,
)


def to_date_str(value: Any) -> str | None:
    """date / datetime / str 统一成 YYYY-MM-DD"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def to_str(value: Any) -> str | None:
    """任意日期/时间类型 → str(供 JSON 返回)"""
    if value is None:
        return None
    return str(value)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_row(row: dict | None) -> dict | None:
    """把行里的 date/datetime 转成字符串,方便直接 JSON 序列化"""
    if not row:
        return row
    out = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def normalize_rows(rows: Iterable[dict]) -> list[dict]:
    return [normalize_row(r) or {} for r in rows]
