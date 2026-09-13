from pathlib import Path

from app.config import load_config


def test_secret_key_generated_and_persisted(tmp_path):
    env_file = tmp_path / ".env"
    cfg = load_config(env_file=env_file)
    assert cfg.secret_key  # 自动生成非空

    cfg2 = load_config(env_file=env_file)
    assert cfg2.secret_key == cfg.secret_key  # 第二次读取复用，不重复生成


def test_reads_env_overrides(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=abc\n", encoding="utf-8")
    monkeypatch.setenv("ADMIN_PASSWORD", "seed-pass")
    cfg = load_config(env_file=env_file)
    assert cfg.secret_key == "abc"
    assert cfg.admin_password == "seed-pass"
    assert cfg.db_path  # 有默认值


def test_mock_flag_passthrough(tmp_path):
    cfg = load_config(mock=True, env_file=tmp_path / ".env")
    assert cfg.mock is True


def test_admin_password_none_when_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    cfg = load_config(env_file=tmp_path / ".env")
    assert cfg.admin_password is None


def test_append_respects_missing_trailing_newline(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DB_PATH=x", encoding="utf-8")  # 无尾换行
    cfg = load_config(env_file=env_file)
    assert cfg.db_path == "x"

    cfg2 = load_config(env_file=env_file)
    assert cfg2.db_path == "x"  # SECRET_KEY 追加未与 DB_PATH 粘连
    assert cfg2.secret_key == cfg.secret_key  # 生成的 SECRET_KEY 可正确读回


def test_cookie_secure_from_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("COOKIE_SECURE=1\n", encoding="utf-8")
    assert load_config(env_file=env).cookie_secure is True


def test_cookie_secure_truthy_variants_and_default(tmp_path, monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)  # 隔离宿主环境变量（CI 可移植）
    env = tmp_path / ".env"
    env.write_text("COOKIE_SECURE=true\n", encoding="utf-8")
    assert load_config(env_file=env).cookie_secure is True
    env.write_text("COOKIE_SECURE=0\n", encoding="utf-8")
    assert load_config(env_file=env).cookie_secure is False
    env.write_text("", encoding="utf-8")
    assert load_config(env_file=env).cookie_secure is False
