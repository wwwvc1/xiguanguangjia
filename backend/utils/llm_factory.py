"""LLM Client 工厂化 - 支持多模型动态加载"""
import time
from typing import Optional
from openai import OpenAI
from database import get_connection
from config import settings


def get_model_by_id(model_id: int) -> Optional[dict]:
    """按 ID 查模型(返回完整记录,含 api_key 等)"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, name, base_url, api_key, model_name, is_system_default, is_active, owner_user_id,
                          created_at, updated_at
                   FROM llm_models WHERE id = %s""",
                (model_id,)
            )
            return cursor.fetchone()
    finally:
        conn.close()


def get_default_model() -> Optional[dict]:
    """查系统默认模型"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, name, base_url, api_key, model_name, is_system_default, is_active, owner_user_id,
                          created_at, updated_at
                   FROM llm_models WHERE is_system_default = 1 AND is_active = 1 LIMIT 1"""
            )
            return cursor.fetchone()
    finally:
        conn.close()


def get_user_active_model(user_id: int) -> Optional[dict]:
    """查用户当前激活的模型(user_settings.active_model_id),fallback 到系统默认"""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT s.active_model_id
                   FROM user_settings s
                   WHERE s.user_id = %s AND s.active_model_id IS NOT NULL""",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row.get("active_model_id"):
                m = get_model_by_id(row["active_model_id"])
                if m and m["is_active"]:
                    # 校验 ownership
                    if m["owner_user_id"] is None or m["owner_user_id"] == user_id:
                        return m
            return get_default_model()
    finally:
        conn.close()


def get_llm_client_for_user(user_id: int, model_id: Optional[int] = None) -> tuple[OpenAI, dict]:
    """
    为用户取 LLM client + 模型信息
    返回 (client, model_record)
    优先级: 入参 model_id > 用户激活 > 系统默认 > 环境变量默认
    """
    model = None
    if model_id:
        model = get_model_by_id(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        if not model["is_active"]:
            raise ValueError(f"模型 {model_id} 已停用")
        # 校验所有权(只能用自己的或系统预设)
        if model["owner_user_id"] is not None and model["owner_user_id"] != user_id:
            raise ValueError("无权使用该模型")

    if not model:
        model = get_user_active_model(user_id)

    if not model:
        # 最后兜底:用环境变量
        client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
        return client, {
            "id": None, "name": "环境变量默认", "model_name": settings.CHAT_MODEL,
            "base_url": settings.OPENAI_BASE_URL, "api_key": settings.OPENAI_API_KEY,
            "is_system_default": False, "owner_user_id": None
        }

    # 若 api_key 是占位符,用 .env 的
    api_key = model["api_key"] if model["api_key"] and model["api_key"] != "MIGRATION_PLACEHOLDER" else settings.OPENAI_API_KEY

    client = OpenAI(api_key=api_key, base_url=model["base_url"])
    return client, model


def test_model_connection(model_id: int, prompt: str = "你好,请用一句话自我介绍。") -> dict:
    """测试模型连通性,返回 {success, latency_ms, reply, error}"""
    model = get_model_by_id(model_id)
    if not model:
        return {"success": False, "latency_ms": 0, "reply": None, "error": "模型不存在"}

    api_key = model["api_key"] if model["api_key"] and model["api_key"] != "MIGRATION_PLACEHOLDER" else settings.OPENAI_API_KEY
    client = OpenAI(api_key=api_key, base_url=model["base_url"], timeout=20.0)

    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=model["model_name"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.5
        )
        latency = int((time.time() - start) * 1000)
        reply = resp.choices[0].message.content if resp.choices else "(空)"
        return {"success": True, "latency_ms": latency, "reply": reply, "error": None}
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {"success": False, "latency_ms": latency, "reply": None, "error": str(e)}


def mask_api_key(api_key: str) -> str:
    """API key 脱敏:前 4 后 4"""
    if not api_key or len(api_key) <= 8:
        return "****" if api_key else ""
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
