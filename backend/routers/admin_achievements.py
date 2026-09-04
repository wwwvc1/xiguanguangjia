"""
Admin 成就定义管理 API
- GET    /api/admin/achievements          列出全部
- GET    /api/admin/achievements/{id}     详情
- POST   /api/admin/achievements          新建
- PUT    /api/admin/achievements/{id}     修改
- DELETE /api/admin/achievements/{id}     删除
- GET    /api/admin/achievements/metrics  列出支持的 metric_type
- GET    /api/admin/achievements/stats    成就解锁统计(按 type)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_connection
from utils.admin_auth import get_current_admin
from utils.achievement_engine import (
    list_definitions, get_definition_by_id
)

router = APIRouter(prefix="/api/admin/achievements", tags=["admin-achievements"])


# 支持的 metric_type + 中文标签 + 单位描述(给前端下拉用)
METRIC_TYPES = [
    {"value": "todo_count",         "label": "创建待办总数",     "unit": "条",  "desc": "累计创建多少条待办"},
    {"value": "done_todo",          "label": "完成待办总数",     "unit": "条",  "desc": "标记完成的待办条数"},
    {"value": "goal_count",         "label": "创建目标总数",     "unit": "个",  "desc": "累计创建多少个目标"},
    {"value": "done_goal",          "label": "完成目标总数",     "unit": "个",  "desc": "完成的目标数"},
    {"value": "tx_count",           "label": "收支记录总数",     "unit": "笔",  "desc": "累计记多少笔账"},
    {"value": "tx_income_total",    "label": "总收入金额",       "unit": "元",  "desc": "累计收入(收入为正数)"},
    {"value": "tx_expense_total",   "label": "总支出金额",       "unit": "元",  "desc": "累计支出(取绝对值)"},
    {"value": "meal_count",         "label": "饮食记录总数",     "unit": "餐",  "desc": "累计记录多少餐"},
    {"value": "early_reminder",     "label": "早起提醒数",       "unit": "个",  "desc": "早于 7:00 的提醒数"},
    {"value": "consecutive_checkin","label": "连续打卡天数",     "unit": "天",  "desc": "连续完成待办的天数"},
]


class AchievementCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = "🏅"
    metric_type: str
    target_value: int = 1
    is_active: int = 1
    sort_order: int = 0


class AchievementUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    metric_type: Optional[str] = None
    target_value: Optional[int] = None
    is_active: Optional[int] = None
    sort_order: Optional[int] = None


@router.get("/metrics")
def list_metrics(_admin=Depends(get_current_admin)):
    """返回支持的 metric_type 列表(给前端下拉)"""
    return {"metrics": METRIC_TYPES}


@router.get("/")
def list_all(_admin=Depends(get_current_admin)):
    """列出所有成就定义"""
    rows = list_definitions(active_only=False)
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = str(r["created_at"])
    return {"items": rows, "total": len(rows)}


# ============================================================
# 成就解锁统计(给 Dashboard 用)
# 必须在 /{ach_id} 之前注册,否则 'stats' 会被当成 ach_id
# ============================================================
class AchievementStatsItem(BaseModel):
    code: str
    name: str
    unlocked_count: int          # 已解锁次数(同一用户多次不算)
    total_users: int             # 平台总用户数(分母)


class AchievementStatsResponse(BaseModel):
    total: int                   # 定义总数
    unlocked: int                # 平台被解锁过的总次数(可能 > total,因为同一用户可解多个)
    by_type: list[AchievementStatsItem]


@router.get("/stats", response_model=AchievementStatsResponse)
def achievement_stats(_admin=Depends(get_current_admin)):
    """成就解锁统计:按 type(code)聚合,count 已解锁人数 + 当前平台用户总数"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 平台总用户数(分母)
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            total_users = int(cursor.fetchone()["c"] or 0)

            # 平台被解锁次数(独立 user_id × type 组合)
            cursor.execute(
                "SELECT COUNT(*) AS c FROM achievements"
            )
            unlocked_total = int(cursor.fetchone()["c"] or 0)

            # 列出所有定义 + 该 code 的去重解锁人数
            cursor.execute(
                """SELECT d.code, d.name,
                          COALESCE(c.unlocked_count, 0) AS unlocked_count
                   FROM achievement_definitions d
                   LEFT JOIN (
                       SELECT type, COUNT(DISTINCT user_id) AS unlocked_count
                       FROM achievements
                       GROUP BY type
                   ) c ON c.type = d.code
                   ORDER BY d.sort_order ASC, d.id ASC"""
            )
            rows = cursor.fetchall()

            items = [
                AchievementStatsItem(
                    code=r["code"],
                    name=r["name"],
                    unlocked_count=int(r["unlocked_count"] or 0),
                    total_users=total_users,
                )
                for r in rows
            ]

            # 统计定义数(只统计 is_active=1 的"在售"成就)
            cursor.execute(
                "SELECT COUNT(*) AS c FROM achievement_definitions WHERE is_active = 1"
            )
            defs_total = int(cursor.fetchone()["c"] or 0)

            return AchievementStatsResponse(
                total=defs_total,
                unlocked=unlocked_total,
                by_type=items,
            )
    finally:
        conn.close()


@router.get("/{ach_id}")
def get_one(ach_id: int, _admin=Depends(get_current_admin)):
    row = get_definition_by_id(ach_id)
    if not row:
        raise HTTPException(404, "成就不存在")
    if row.get("created_at"):
        row["created_at"] = str(row["created_at"])
    return row


@router.post("/")
def create(payload: AchievementCreate, admin=Depends(get_current_admin)):
    """新建成就定义"""
    # 校验 metric_type
    valid_metrics = {m["value"] for m in METRIC_TYPES}
    if payload.metric_type not in valid_metrics:
        raise HTTPException(400, f"metric_type 必须是 {sorted(valid_metrics)} 之一")
    if not payload.code or not payload.name:
        raise HTTPException(400, "code 和 name 必填")
    if payload.target_value < 1:
        raise HTTPException(400, "target_value 必须 >= 1")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM achievement_definitions WHERE code = %s",
                (payload.code,)
            )
            if cur.fetchone():
                raise HTTPException(400, f"code '{payload.code}' 已存在")
            cur.execute(
                """INSERT INTO achievement_definitions
                   (code, name, description, icon, metric_type, target_value, is_active, sort_order, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (payload.code, payload.name, payload.description, payload.icon or "🏅",
                 payload.metric_type, payload.target_value, int(payload.is_active),
                 payload.sort_order, admin["id"])
            )
            new_id = cur.lastrowid
            conn.commit()
    finally:
        conn.close()
    row = get_definition_by_id(new_id)
    return row


@router.put("/{ach_id}")
def update(ach_id: int, payload: AchievementUpdate, _admin=Depends(get_current_admin)):
    """修改成就定义"""
    existing = get_definition_by_id(ach_id)
    if not existing:
        raise HTTPException(404, "成就不存在")
    # 不允许改 code(防止已有用户解锁记录失效)
    updates = {}
    if payload.name is not None: updates["name"] = payload.name
    if payload.description is not None: updates["description"] = payload.description
    if payload.icon is not None: updates["icon"] = payload.icon
    if payload.metric_type is not None:
        valid = {m["value"] for m in METRIC_TYPES}
        if payload.metric_type not in valid:
            raise HTTPException(400, f"metric_type 必须是 {sorted(valid)} 之一")
        updates["metric_type"] = payload.metric_type
    if payload.target_value is not None:
        if payload.target_value < 1:
            raise HTTPException(400, "target_value 必须 >= 1")
        updates["target_value"] = payload.target_value
    if payload.is_active is not None: updates["is_active"] = int(payload.is_active)
    if payload.sort_order is not None: updates["sort_order"] = payload.sort_order
    if not updates:
        raise HTTPException(400, "没有提供修改字段")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [ach_id]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE achievement_definitions SET {set_clause} WHERE id = %s",
                values
            )
            conn.commit()
    finally:
        conn.close()
    return get_definition_by_id(ach_id)


@router.delete("/{ach_id}")
def delete(ach_id: int, _admin=Depends(get_current_admin)):
    """删除成就定义(同时清掉所有用户的解锁记录)"""
    existing = get_definition_by_id(ach_id)
    if not existing:
        raise HTTPException(404, "成就不存在")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM achievements WHERE type = %s", (existing["code"],))
            cur.execute("DELETE FROM achievement_definitions WHERE id = %s", (ach_id,))
            conn.commit()
    finally:
        conn.close()
    return {"ok": True, "deleted_id": ach_id}
