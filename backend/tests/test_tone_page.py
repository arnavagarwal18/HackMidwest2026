"""GET /tone serves frontend/tone.html (the contract's address for the phone tone page)."""
from fastapi.testclient import TestClient

from app import tone_page
from app.main import app


def test_tone_serves_the_tone_page_whatever_the_query():
    response = TestClient(app).get("/tone?instrument=trumpet&note=Bb3")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == TestClient(app).get("/tone.html").text


def test_tone_works_without_a_query():
    assert TestClient(app).get("/tone").status_code == 200


def test_a_missing_tone_page_is_a_500_server_error_and_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(tone_page, "TONE_PAGE", tone_page.TONE_PAGE.with_name("missing.html"))
    response = TestClient(app, raise_server_exceptions=False).get("/tone")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "server_error"
    assert "missing" in caplog.text
