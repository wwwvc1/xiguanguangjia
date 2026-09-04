"""用户端 LLM 模型管理 - 自定义(最多 3 个)"""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_connection
from utils.deps import get_current_user
from utils.llm_factory import get_model_by_id, get_default_model, mask_api_key

router = APIRouter(prefix="/api/llm/models", tags=["user-llm"])


class UserModelCreate(BaseModel):
    name: str
    base_url: str
    api_key: str
    model_name: str


class UserModelUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    is_active: Optional[bool] = None


def _to_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "model_name": row["model_name"],
        "is_active": bool(row.get("is_active")),
        "owner_user_id": row.get("owner_user_id"),
        "is_system_default": bool(row.get("is_system_default")),
        "api_key_masked": mask_api_key(row["api_key"])
    }


def _ensure_settings(user_id: int):
    """确保 user_settings 行存在"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM user_settings WHERE user_id = %s", (user_id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user_settings (user_id, target_calories) VALUES (%s, 1800)", (user_id,))
                conn.commit()
    finally:
        conn.close()


@router.get("/available")
def get_available_models(current_user: int = Depends(get_current_user)):
    """当前用户可见的全部模型:系统预设 + 自己的(最多 3 个)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM llm_models
                   WHERE (owner_user_id IS NULL OR owner_user_id = %s)
                   ORDER BY is_system_default DESC, id ASC""",
                (current_user,)
            )
            models = [_to_response(r) for r in cursor.fetchall()]
            cursor.execute("SELECT active_model_id FROM user_settings WHERE user_id = %s", (current_user,))
            row = cursor.fetchone()
            return {
                "models": models,
                "active_model_id": row["active_model_id"] if row else None
            }
    finally:
        conn.close()


@router.post("/user")
def create_user_model(payload: UserModelCreate, current_user: int = Depends(get_current_user)):
    """用户新增自定义模型(最多 3 个)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS c FROM llm_models WHERE owner_user_id = %s AND is_active = 1",
                (current_user,)
            )
            cnt = cursor.fetchone()["c"]
            if cnt >= 3:
                raise HTTPException(status_code=400, detail="最多只能添加 3 个自定义模型")
            cursor.execute(
                """INSERT INTO llm_models (name, base_url, api_key, model_name, is_system_default, is_active, owner_user_id)
                   VALUES (%s, %s, %s, %s, 0, 1, %s)""",
                (payload.name, payload.base_url, payload.api_key, payload.model_name, current_user)
            )
            model_id = cursor.lastrowid
            conn.commit()
            return _to_response(get_model_by_id(model_id))
    finally:
        conn.close()


@router.put("/user/{model_id}")
def update_user_model(model_id: int, payload: UserModelUpdate, current_user: int = Depends(get_current_user)):
    existing = get_model_by_id(model_id)
    if not existing or existing["owner_user_id"] != current_user:
        raise HTTPException(status_code=404, detail="模型不存在或无权操作")
    updates = {}
    if payload.name is not None: updates["name"] = payload.name
    if payload.base_url is not None: updates["base_url"] = payload.base_url
    if payload.api_key is not None: updates["api_key"] = payload.api_key
    if payload.model_name is not None: updates["model_name"] = payload.model_name
    if payload.is_active is not None: updates["is_active"] = int(payload.is_active)
    if not updates:
        raise HTTPException(status_code=400, detail="没有更新字段")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [model_id]
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"UPDATE llm_models SET {set_clause} WHERE id = %s AND owner_user_id = %s",
                           values + [current_user])
            conn.commit()
            return _to_response(get_model_by_id(model_id))
    finally:
        conn.close()


@router.delete("/user/{model_id}")
def delete_user_model(model_id: int, current_user: int = Depends(get_current_user)):
    existing = get_model_by_id(model_id)
    if not existing or existing["owner_user_id"] != current_user:
        raise HTTPException(status_code=404, detail="模型不存在或无权操作")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM llm_models WHERE id = %s AND owner_user_id = %s", (model_id, current_user))
            # 如果删的是当前激活,清空 active_model_id
            cursor.execute("UPDATE user_settings SET active_model_id = NULL WHERE user_id = %s AND active_model_id = %s",
                           (current_user, model_id))
            conn.commit()
            return {"message": "已删除"}
    finally:
        conn.close()


@router.post("/user/{model_id}/activate")
def activate_user_model(model_id: int, current_user: int = Depends(get_current_user)):
    """设为当前激活"""
    existing = get_model_by_id(model_id)
    if not existing or not existing["is_active"]:
        raise HTTPException(status_code=404, detail="模型不存在或已停用")
    if existing["owner_user_id"] is not None and existing["owner_user_id"] != current_user:
        raise HTTPException(status_code=403, detail="无权使用该模型")
    _ensure_settings(current_user)
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE user_settings SET active_model_id = %s WHERE user_id = %s",
                           (model_id, current_user))
            conn.commit()
            return {"message": "已激活", "active_model_id": model_id}
    finally:
        conn.close()
