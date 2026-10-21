"""AI 工具写库后的缓存失效

## 为什么需要这个

AI 链路(agent / 多任务)的工具是**直接操作数据库**的,不经过 routers。
它们完全没有调用 `cache.abump`,后果是:

    用户在 AI 里说"加一个待办" → 数据库写成功了
    → 但 `hb:dash:{uid}:{date}` 还是旧的,60 秒内首页看不到
    → `hb:stats:patterns:{uid}` 300 秒内还是旧的

实测就是「agent 生成的任务首页没及时刷新」。

## 做法

不逐个改 25 个工具函数,而是**按工具名推导**:
- 写动词前缀(add_/update_/delete_/toggle_/batch_…)判定是不是写操作
- 名字里的名词(todo/goal/transaction/meal/reminder/settings)判定改动哪个域

这样以后新增工具不用改这里,只要命名符合 `动词_名词` 约定。
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from core import cache

log = logging.getLogger("services.cache_invalidation")

# 读操作前缀:不需要失效
_READ_PREFIXES = ("list_", "get_", "aggregate_", "search_", "query_", "find_", "count_")

# 写操作前缀
_WRITE_PREFIXES = (
    "add_", "create_", "update_", "delete_", "remove_",
    "toggle_", "complete_", "batch_", "set_", "mark_", "upsert_",
)

# 工具名关键词 → 缓存域(顺序有意义,先匹配更具体的)
_DOMAIN_RULES = (
    ("transaction", "tx"),
    ("expense", "tx"),
    ("income", "tx"),
    ("todo", "todo"),
    ("task", "todo"),
    ("goal", "goal"),
    ("meal", "meal"),
    ("diet", "meal"),
    ("reminder", "reminder"),
    ("checkin", "checkin"),
    ("setting", "settings"),
    ("achievement", "achievement"),
)


def is_write_tool(tool_name: str) -> bool:
    """是不是写操作工具"""
    name = (tool_name or "").lower()
    if not name:
        return False
    if name.startswith(_READ_PREFIXES):
        return False
    return name.startswith(_WRITE_PREFIXES)


def domain_for_tool(tool_name: str) -> Optional[str]:
    """从工具名推出缓存域"""
    name = (tool_name or "").lower()
    for keyword, domain in _DOMAIN_RULES:
        if keyword in name:
            return domain
    return None


def bump_for_tool(user_id: int, tool_name: str) -> list[str]:
    """写工具执行成功后调用。返回被失效的域(空列表表示不是写操作)。"""
    if not is_write_tool(tool_name):
        return []

    domain = domain_for_tool(tool_name)
    if not domain:
        # 认不出域就别乱失效(会把缓存命中率打没),但要留痕方便补规则
        log.warning("工具 %s 判定为写操作,但无法映射缓存域,已跳过失效", tool_name)
        return []

    try:
        cache.bump(user_id, domain)
    except Exception as e:  # 缓存不可用时不影响主流程
        log.debug("bump 缓存失败(忽略): %s", e)
        return []

    return [domain]


# 给前端/文档用的正则说明:工具名遵循 `动词_名词`
WRITE_TOOL_PATTERN = re.compile(r"^(add|create|update|delete|remove|toggle|complete|batch|set|mark|upsert)_")


__all__ = [
    "is_write_tool", "domain_for_tool", "bump_for_tool", "WRITE_TOOL_PATTERN",
]
