"""The portal must be served by the same app as the JSON API (EF-VAL-01)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.fakes.fake_store import FakeStore

from marge.api import create_app
from marge.api.app import DEFAULT_PORTAL_DIR, mount_portal

HEADERS = {"X-Actor-Id": "controller-01", "X-Actor-Role": "CONTROLLER"}


def test_root_serves_the_portal_html() -> None:
    client = TestClient(create_app(store=FakeStore()))
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_the_json_api_still_answers_next_to_the_portal() -> None:
    client = TestClient(create_app(store=FakeStore()))
    response = client.get("/v1/contracts", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_static_assets_are_reachable() -> None:
    client = TestClient(create_app(store=FakeStore()))
    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_a_missing_portal_directory_does_not_break_the_api(tmp_path) -> None:
    app = create_app(store=FakeStore(), portal_dir=tmp_path / "absent")
    client = TestClient(app)
    assert client.get("/v1/coverage", headers=HEADERS).status_code == 200
    assert client.get("/").status_code == 404


def test_mount_portal_returns_the_directory_it_serves(tmp_path) -> None:
    from fastapi import FastAPI

    portal = tmp_path / "portal"
    portal.mkdir()
    (portal / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    app = FastAPI()
    assert mount_portal(app, portal) == portal
    assert TestClient(app).get("/").status_code == 200


def test_mount_portal_without_index_html_is_a_noop(tmp_path) -> None:
    from fastapi import FastAPI

    app = FastAPI()
    assert mount_portal(app, tmp_path) is None


def test_the_default_portal_directory_exists() -> None:
    assert (DEFAULT_PORTAL_DIR / "index.html").is_file()
