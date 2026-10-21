"""我现在到底在用哪个模型?

把 `llm_models` 的优先级链完整打印出来,并指出**最终生效的来源**。
改完 .env 没反应的时候先跑这个。

用法: cd backend && python scripts/which_model.py [user_id]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from repositories import llm_repo

SEP = "=" * 66


def mask(k: str) -> str:
    if not k:
        return "(空)"
    return k[:6] + "*" * max(0, len(k) - 10) + k[-4:] if len(k) > 10 else "****"


def show(title: str, row: dict | None):
    print(f"\n{title}")
    if not row:
        print("    (无)")
        return
    print(f"    id           : {row.get('id')}")
    print(f"    name         : {row.get('name')}")
    print(f"    model_name   : {row.get('model_name')}")
    print(f"    base_url     : {row.get('base_url')}")
    print(f"    api_key      : {mask(row.get('api_key') or '')}")
    print(f"    is_active    : {row.get('is_active')}")
    print(f"    system_default: {row.get('is_system_default')}")
    print(f"    owner_user_id: {row.get('owner_user_id')}")


def main(user_id: int):
    print(SEP)
    print(".env 里的兜底配置")
    print(SEP)
    print(f"    OPENAI_BASE_URL : {settings.OPENAI_BASE_URL}")
    print(f"    OPENAI_API_KEY  : {mask(settings.OPENAI_API_KEY)}")
    print(f"    CHAT_MODEL      : {settings.CHAT_MODEL}")
    print(f"    LLM_BACKEND     : {settings.LLM_BACKEND}")

    print(f"\n{SEP}")
    print("llm_models 表(库里的配置)")
    print(SEP)
    print(f"    {'id':<4}{'name':<20}{'model_name':<24}{'default':<9}{'active':<7}base_url")
    for m in _all_models():
        print(f"    {m['id']:<4}{(m['name'] or '')[:19]:<20}{(m['model_name'] or '')[:23]:<24}"
              f"{'YES' if m['is_system_default'] else '-':<9}"
              f"{'YES' if m['is_active'] else '-':<7}{m['base_url']}")

    # ---- 按真实优先级解析 ----
    print(f"\n{SEP}")
    print(f"实际生效的模型(以 user_id={user_id} 为例)")
    print(SEP)

    active_id = llm_repo.active_model_id_sync(user_id)
    print(f"\n    ① 用户激活模型 user_settings.active_model_id = {active_id}")

    if active_id:
        pinned = llm_repo.model_by_id_sync(active_id)
        show("    → 用户设置的模型", pinned)
        if pinned and pinned["is_active"]:
            print("\n    ✅ 最终使用:   用户自己的选择(user_settings.active_model_id)")
            return

    default = llm_repo.default_model_sync()
    show("    ② 系统默认模型 llm_models.is_system_default=1", default)
    if default:
        print("\n    ✅ 最终使用:   系统默认模型(⭐ .env 在这里不生效)")
        print("       想换模型 → 改库里这条 / 用管理后台 set-default")
        return

    print("\n    ③ 环境变量兜底")

    print("\n    ✅ 最终使用:   .env 的配置(库里没有可用默认模型)")
    print("       想换模型 → 改 backend/.env 三行,或往库里加一条并设为默认")


def _all_models():
    from core.database import get_sync_connection
    conn = get_sync_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, model_name, base_url, api_key, is_active, "
                "is_system_default, owner_user_id FROM llm_models ORDER BY id")
            return cur.fetchall()
    finally:
        conn.close()


if __name__ == "__main__":
    uid = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    main(uid)
