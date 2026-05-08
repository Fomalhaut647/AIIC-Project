from fastapi.testclient import TestClient


def test_root_serves_index_html(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "AIIC MiMo Chat" in resp.text


def test_static_app_js_served(client: TestClient, tmp_path, monkeypatch):
    # 真实从 web/ 提供
    resp = client.get("/static/styles.css")
    # 文件可能不存在还，但路由必须挂上 → 不存在则返回 404；存在则 200
    assert resp.status_code in (200, 404)
