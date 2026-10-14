from fastapi.testclient import TestClient

from failsight import __version__
from failsight.server import create_app


def test_health():
    client = TestClient(create_app())
    assert client.get("/api/health").json() == {"status": "ok", "version": __version__}


def test_placeholder_when_ui_not_built(tmp_path):
    client = TestClient(create_app(static_dir=tmp_path))
    response = client.get("/")
    assert response.status_code == 200
    assert "UI has not been built" in response.text


def test_serves_built_ui(tmp_path):
    (tmp_path / "index.html").write_text("<p>canvas</p>")
    client = TestClient(create_app(static_dir=tmp_path))
    assert client.get("/").text == "<p>canvas</p>"
