"""待办 CRUD 测试"""
import pytest


@pytest.fixture
def todo_id(api):
    """创建一个 todo,返回 id,测试结束后删除"""
    r = api.post(f"{api.base_url}/todos/", json={"text": "pytest 临时 todo"})
    assert r.status_code == 200, f"创建 todo 失败: {r.text}"
    _id = r.json()["id"]
    yield _id
    # 清理
    api.delete(f"{api.base_url}/todos/{_id}")


@pytest.mark.smoke
@pytest.mark.crud
def test_create_todo(api):
    """创建 todo"""
    r = api.post(f"{api.base_url}/todos/", json={"text": "测试创建"})
    assert r.status_code == 200
    assert r.json()["text"] == "测试创建"
    assert r.json()["done"] == 0
    # 清理
    api.delete(f"{api.base_url}/todos/{r.json()['id']}")


@pytest.mark.crud
def test_list_todos(api):
    """列出 todo"""
    r = api.get(f"{api.base_url}/todos/?done=false")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.crud
def test_toggle_todo(api, todo_id):
    """勾选/取消 todo(用 PUT)"""
    # 勾选
    r = api.put(f"{api.base_url}/todos/{todo_id}", json={"done": True})
    assert r.status_code == 200
    assert r.json()["done"] == 1
    # 取消
    r = api.put(f"{api.base_url}/todos/{todo_id}", json={"done": False})
    assert r.status_code == 200
    assert r.json()["done"] == 0


@pytest.mark.crud
def test_delete_todo(api):
    """删除 todo"""
    r = api.post(f"{api.base_url}/todos/", json={"text": "要删的"})
    _id = r.json()["id"]
    r2 = api.delete(f"{api.base_url}/todos/{_id}")
    assert r2.status_code == 200
    # 再次 GET 应 404 或 200(空)
    r3 = api.get(f"{api.base_url}/todos/?done=false")
    assert all(t["id"] != _id for t in r3.json())


@pytest.mark.crud
def test_create_empty_text_fails(api):
    """空文本创建应 422"""
    r = api.post(f"{api.base_url}/todos/", json={"text": ""})
    assert r.status_code in (400, 422)
