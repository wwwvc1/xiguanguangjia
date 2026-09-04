"""管理员 LLM 模型管理"""
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from database import get_connection
from utils.admin_auth import get_current_admin
from utils.operation_logger import log_admin_action
from utils.llm_factory import (
    get_model_by_id, get_default_model,
    test_model_connection, mask_api_key
)
from models.llm_model import (
    LLMModelCreate, LLMModelUpdate, LLMModelResponse,
    LLMModelTestRequest, LLMModelTestResponse
)

router = APIRouter(prefix="/api/admin/llm-models", tags=["admin-llm"])


def _to_response(row: dict) -> LLMModelResponse:
    return LLMModelResponse(
        id=row["id"],
        name=row["name"],
        base_url=row["base_url"],
        api_key=row["api_key"],
        model_name=row["model_name"],
        is_system_default=bool(row.get("is_system_default")),
        is_active=bool(row.get("is_active")),
        owner_user_id=row.get("owner_user_id"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        api_key_masked=mask_api_key(row["api_key"])
    )


@router.get("", response_model=List[LLMModelResponse])
def list_models(
    owner: Optional[str] = Query(None, description="system|user|all"),
    is_active: Optional[bool] = Query(None),
    admin: dict = Depends(get_current_admin)
):
    where = ["1=1"]
    params: list = []
    if owner == "system":
        where.append("owner_user_id IS NULL")
    elif owner == "user":
        where.append("owner_user_id IS NOT NULL")
    if is_active is not None:
        where.append("is_active = %s")
        params.append(int(is_active))
    sql = "SELECT * FROM llm_models WHERE " + " AND ".join(where) + " ORDER BY is_system_default DESC, id ASC"
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            return [_to_response(r) for r in cursor.fetchall()]
    finally:
        conn.close()


@router.post("", response_model=LLMModelResponse)
def create_model(payload: LLMModelCreate, request: Request, admin: dict = Depends(get_current_admin)):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            # 如要设为系统默认,先取消其他
            if payload.is_system_default:
                cursor.execute("UPDATE llm_models SET is_system_default = 0")
            cursor.execute(
                """INSERT INTO llm_models (name, base_url, api_key, model_name, is_system_default, is_active, owner_user_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (payload.name, payload.base_url, payload.api_key, payload.model_name,
                 int(payload.is_system_default), int(payload.is_active), payload.owner_user_id)
            )
            model_id = cursor.lastrowid
            conn.commit()
            row = get_model_by_id(model_id)
            log_admin_action(request, admin, "create_llm_model", "llm_model", model_id,
                             {"name": payload.name, "is_system_default": payload.is_system_default})
            return _to_response(row)
    finally:
        conn.close()


@router.put("/{model_id}", response_model=LLMModelResponse)
def update_model(model_id: int, payload: LLMModelUpdate, request: Request, admin: dict = Depends(get_current_admin)):
    existing = get_model_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模型不存在")
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
            cursor.execute(f"UPDATE llm_models SET {set_clause} WHERE id = %s", values)
            conn.commit()
            log_admin_action(request, admin, "update_llm_model", "llm_model", model_id, list(updates.keys()))
            row = get_model_by_id(model_id)
            return _to_response(row)
    finally:
        conn.close()


@router.delete("/{model_id}")
def delete_model(model_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    existing = get_model_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模型不存在")
    if existing["is_system_default"]:
        raise HTTPException(status_code=400, detail="系统默认模型不能删除,可改为停用")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM llm_models WHERE id = %s", (model_id,))
            conn.commit()
            log_admin_action(request, admin, "delete_llm_model", "llm_model", model_id, {"name": existing["name"]})
            return {"message": "已删除"}
    finally:
        conn.close()


@router.post("/{model_id}/set-default")
def set_default_model(model_id: int, request: Request, admin: dict = Depends(get_current_admin)):
    existing = get_model_by_id(model_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模型不存在")
    if not existing["is_active"]:
        raise HTTPException(status_code=400, detail="模型已停用,无法设为默认")
    if existing["owner_user_id"] is not None:
        raise HTTPException(status_code=400, detail="用户私有模型不能设为系统默认")
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE llm_models SET is_system_default = 0")
            cursor.execute("UPDATE llm_models SET is_system_default = 1 WHERE id = %s", (model_id,))
            conn.commit()
            log_admin_action(request, admin, "set_default_llm_model", "llm_model", model_id)
            return {"message": "已设为系统默认", "model_id": model_id}
    finally:
        conn.close()


@router.post("/{model_id}/test", response_model=LLMModelTestResponse)
def test_model(model_id: int, payload: LLMModelTestRequest, admin: dict = Depends(get_current_admin)):
    r = test_model_connection(model_id, payload.prompt)
    return LLMModelTestResponse(**r)
