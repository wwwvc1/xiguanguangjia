"""用户资料 API — 昵称 + 头像(base64)
异步版,与 routers/user_settings.py 共享 /api/user 前缀
"""
import base64
import re
from fastapi import APIRouter, Depends, HTTPException
from aiomysql import DictCursor
from database import get_conn
from models.user import UserResponse, ProfileUpdate
from utils.deps import get_current_user

router = APIRouter(prefix="/api/user", tags=["user_profile"])

# base64 头部正则:data:image/<mime>;base64,
_DATA_URL_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,(.+)$")
# 单张头像 base64 解码后 ≤ 2 MB
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def _normalize_avatar(raw: str | None) -> str | None:
    """校验 + 规范化 base64 头像;空值表示清空,返回 None 表示清空,非空字符串为存库值"""
    if raw is None:
        return None  # 字段未提供
    if raw == "":
        return None  # 显式清空

    payload = raw
    m = _DATA_URL_RE.match(raw.strip())
    if m:
        payload = m.group(1).strip()

    # 校验字符 + 长度(4 的倍数才合法)
    payload = re.sub(r"\s+", "", payload)
    if not payload:
        raise HTTPException(status_code=400, detail="avatar base64 内容为空")
    if len(payload) % 4 != 0:
        raise HTTPException(status_code=400, detail="avatar base64 长度非法(需 4 的倍数)")
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", payload):
        raise HTTPException(status_code=400, detail="avatar 包含非 base64 字符")

    try:
        decoded = base64.b64decode(payload, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="avatar base64 解码失败")

    if len(decoded) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail=f"avatar 解码后超过 {MAX_AVATAR_BYTES // 1024 // 1024} MB")

    return payload


def _normalize_nickname(raw: str | None) -> str | None:
    """空串清空,去首尾空白,长度 1-64"""
    if raw is None:
        return None
    if raw == "":
        return None
    name = raw.strip()
    if not name:
        return None
    if len(name) > 64:
        raise HTTPException(status_code=400, detail="nickname 长度不能超过 64")
    return name


@router.get("/profile", response_model=UserResponse)
async def get_my_profile(current_user: int = Depends(get_current_user)):
    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                "SELECT id, nickname, avatar, created_at FROM users WHERE id = %s",
                (current_user,),
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户不存在")
            return row


@router.put("/profile", response_model=UserResponse)
async def update_my_profile(payload: ProfileUpdate, current_user: int = Depends(get_current_user)):
    new_nick = _normalize_nickname(payload.nickname)
    new_avatar = _normalize_avatar(payload.avatar)

    # 两个字段都没传,直接返回当前数据(等价于空写)
    if new_nick is None and payload.nickname is None and new_avatar is None and payload.avatar is None:
        return await get_my_profile(current_user=current_user)

    updates: dict = {}
    # 判断用户是否真的提供了字段(区分 None=未传 与 None=清空)
    if payload.nickname is not None:
        updates["nickname"] = new_nick  # new_nick 已经是 None/str
    if payload.avatar is not None:
        updates["avatar"] = new_avatar

    if not updates:
        return await get_my_profile(current_user=current_user)

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [current_user]

    async with get_conn() as conn:
        async with conn.cursor(DictCursor) as cur:
            await cur.execute(
                f"UPDATE users SET {set_clause} WHERE id = %s",
                values,
            )
            await conn.commit()

            await cur.execute(
                "SELECT id, nickname, avatar, created_at FROM users WHERE id = %s",
                (current_user,),
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="用户不存在")
            return row
