from fastapi.testclient import TestClient

from app.main import DIST, app

client = TestClient(app)


def test_health_without_database():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] in {"not_configured", "ok", "unavailable"}


def test_unknown_api_route_is_json_404():
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")


def test_openapi_docs_available():
    assert client.get("/api/openapi.json").status_code == 200


def test_spa_fallback_and_assets():
    if not (DIST / "index.html").is_file():
        return  # frontend not built in this environment
    root = client.get("/")
    assert root.status_code == 200 and "<div id=\"root\">" in root.text
    assert client.get("/some/client/route").text == root.text
    asset = next((DIST / "assets").glob("*.js")).name
    res = client.get(f"/assets/{asset}")
    assert res.status_code == 200 and "immutable" in res.headers["cache-control"]


def test_path_traversal_is_blocked():
    res = client.get("/..%2F..%2Fbackend%2Fapp%2Fconfig.py")
    assert "BaseSettings" not in res.text
