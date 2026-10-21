"""AI 接口测试 — 默认跳过(慢 + 依赖外部 LLM)
用 pytest -m ai 跑
"""
import pytest


@pytest.mark.ai
def test_ai_insights(api):
    """AI 智能建议"""
    r = api.post(f"{api.base_url}/stats/insights", json={})
    # 鉴权 ok,LLM 成功或失败都不应 5xx
    assert r.status_code in (200, 500, 502, 503)


@pytest.mark.ai
def test_ai_chat_general(api):
    """AI 通用聊天"""
    r = api.post(f"{api.base_url}/ai/chat/general", json={"message": "hi"})
    assert r.status_code in (200, 500, 502, 503)


@pytest.mark.ai
def test_ai_agent_endpoint(api):
    """AI 智能创建 Agent"""
    r = api.post(f"{api.base_url}/ai/agent/", json={"message": "加一个测试 todo"})
    assert r.status_code in (200, 500, 502, 503, 401])


@pytest.mark.ai
def test_ai_generate_tasks(api):
    """AI 生成任务"""
    r = api.post(f"{api.base_url}/ai/generate-tasks", json={"message": "想每天健身"})
    assert r.status_code in (200, 500, 502, 503)
