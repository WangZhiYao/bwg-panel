import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SPAStaticFiles


@pytest.fixture
def spa_app(tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=str(tmp_path), html=True))
    return app


def test_deep_link_falls_back_to_index(spa_app):
    with TestClient(spa_app) as c:
        r = c.get("/trends")
        assert r.status_code == 200
        assert "spa" in r.text


def test_api_unknown_stays_404(spa_app):
    with TestClient(spa_app) as c:
        assert c.get("/api/no-such").status_code == 404


def test_real_asset_served(spa_app):
    with TestClient(spa_app) as c:
        assert c.get("/app.js").status_code == 200
