from fastapi.testclient import TestClient


def test_root_serves_index_html(client: TestClient):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "AIIC MiMo Chat" in resp.text


def test_static_styles_css_served(client: TestClient):
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "") or resp.headers.get("content-type", "").startswith("text/")


def test_static_app_js_served(client: TestClient):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
