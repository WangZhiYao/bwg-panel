import pytest
from fastapi.testclient import TestClient

from app.kiwivm import mock as kvmmock
from app.main import create_app


@pytest.fixture(autouse=True)
def _clean_kiwivm_mock_state():
    """每个测试前后清空 mock 客户端的模块级电源/快照状态（防跨文件泄漏）。"""
    kvmmock._reset()
    yield
    kvmmock._reset()


@pytest.fixture
def make_app(tmp_path):
    def _make(**kw):
        kw.setdefault("db_path", str(tmp_path / "panel.db"))
        kw.setdefault("secret_key", "test-secret")
        kw.setdefault("admin_password", "pass1234")
        kw.setdefault("start_scheduler", False)
        kw.setdefault("mock", False)  # 默认不播种 Mock 服务器；需要假数据的测试显式传 mock=True
        return create_app(**kw)
    return _make


@pytest.fixture
def client(make_app):
    app = make_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_client(make_app):
    """mock 模式：lifespan 会播种 Mock-A / Mock-B 两台服务器（id 1/2）。"""
    app = make_app(mock=True)
    with TestClient(app) as c:
        yield c
