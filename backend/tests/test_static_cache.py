"""The front-end static mount must make browsers revalidate; API routes must not be touched."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_is_served_with_no_cache():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_js_file_is_served_with_no_cache():
    response = client.get("/js/chat/model.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_unchanged_js_file_revalidates_to_304_with_no_cache():
    etag = client.get("/js/chat/model.js").headers["etag"]
    response = client.get("/js/chat/model.js", headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.headers["cache-control"] == "no-cache"


def test_api_route_does_not_get_the_static_cache_header():
    response = client.post("/sessions", json={"instrument": "violin"})
    assert response.status_code == 201
    assert "cache-control" not in response.headers
