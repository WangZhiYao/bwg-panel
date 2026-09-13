"""面板配置：.env 读取、SECRET_KEY 自动生成并写回。"""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

_BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    db_path: str
    secret_key: str
    admin_password: str | None  # 首次启动种子密码；None 则自动生成打印
    mock: bool
    cookie_secure: bool = False


def load_config(mock: bool = False, env_file: Path | None = None) -> Config:
    env_file = env_file or (_BACKEND_DIR / ".env")
    # 统一取值链：env 文件值 → 进程环境变量 → 默认值/生成。
    # 仅读取，不向进程环境写入（无 load_dotenv 副作用）。
    file_values = dotenv_values(env_file) if env_file.exists() else {}

    def resolve(key: str) -> str | None:
        return file_values.get(key) or os.getenv(key)

    secret_key = resolve("SECRET_KEY") or ""
    if not secret_key:
        secret_key = secrets.token_urlsafe(32)
        # 若文件存在且末尾无换行符，先补换行再追加，避免与原内容粘连。
        prefix = ""
        if env_file.exists() and env_file.stat().st_size > 0:
            with open(env_file, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    prefix = "\n"
        with open(env_file, "a", encoding="utf-8") as f:
            f.write(f"{prefix}SECRET_KEY={secret_key}\n")
    db_path = resolve("DB_PATH") or str(_BACKEND_DIR / "data" / "panel.db")
    admin_password = resolve("ADMIN_PASSWORD") or None
    cookie_secure = (resolve("COOKIE_SECURE") or "").strip().lower() in ("1", "true", "yes", "on")
    return Config(
        db_path=db_path,
        secret_key=secret_key,
        admin_password=admin_password,
        mock=mock,
        cookie_secure=cookie_secure,
    )
