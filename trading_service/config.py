from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Trading Service 配置。"""

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False

    # 数据库配置（共享 SQLite）
    db_path: str = str(Path.home() / "projects" / "news-service" / "news.db")

    # News Service API 配置
    news_service_base_url: str = "http://127.0.0.1:8000"
    news_service_timeout: int = 30

    # 交易所配置
    binance_api_key: str = ""
    binance_api_secret: str = ""

    class Config:
        env_prefix = "TRADING_"
        env_file = ".env"


settings = Settings()

# 确保 DB 路径存在
DB_PARENT = Path(settings.db_path).parent
DB_PARENT.mkdir(parents=True, exist_ok=True)
