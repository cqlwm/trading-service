from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import YamlConfigSettingsSource


class Settings(BaseSettings):
    """Trading Service 配置。

    配置加载优先级（从高到低）：
    1. 环境变量（TRADING_ 前缀）
    2. config.local.yaml（本地配置，不提交到 git）
    3. config.yaml（默认配置，提交到 git）
    4. 默认值
    """

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8001
    debug: bool = False

    # 数据库配置（共享 SQLite）
    db_path: str = str(Path.home() / "projects" / "db" / "news.db")

    # News Service API 配置
    news_service_base_url: str = "http://127.0.0.1:8000"
    news_service_timeout: int = 30

    # 交易所配置
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # LLM 配置（OpenAI 兼容 API，支持 DeepSeek、通义千问等）
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # 贴文配置
    posts_dir: str = "~/projects/trading-service/mydata/posts"
    posts_enabled: bool = True  # 总开关，llm_api_key 为空时自动跳过

    # postx 发布配置（发布到 Binance Square，依赖 binance-service 包）
    postx_enabled: bool = False  # 总开关，默认关闭；开启后 LLM 生成贴文自动截图发帖
    # binance-service 配置文件路径（postx 发布功能依赖，含 chrome/poster/screenshot 等完整配置）
    postx_config_path: str = "/Users/li/projects/binance-service/config.yaml"
    postx_timeframe: str = "1h"  # K 线周期: 5m/15m/1h/4h/1d/1w
    postx_debug: bool = False  # 调试模式（保存调试截图）

    model_config = SettingsConfigDict(
        env_prefix="TRADING_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type["BaseSettings"],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """自定义配置源加载顺序。"""
        sources = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]

        # 优先加载本地配置文件（如果存在）
        local_config = Path("config.local.yaml")
        if local_config.exists():
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_file=str(local_config))
            )

        # 然后加载默认配置文件
        default_config = Path("config.yaml")
        if default_config.exists():
            sources.append(
                YamlConfigSettingsSource(settings_cls, yaml_file=str(default_config))
            )

        sources.append(file_secret_settings)
        return tuple(sources)


settings = Settings()

# 展开 db_path 中的 ~ 为实际 home 路径（SQLAlchemy 不会自动展开）
settings.db_path = str(Path(settings.db_path).expanduser())

# 确保 DB 路径存在
DB_PARENT = Path(settings.db_path).parent
DB_PARENT.mkdir(parents=True, exist_ok=True)

# 展开贴文目录路径并确保目录存在
settings.posts_dir = str(Path(settings.posts_dir).expanduser())
Path(settings.posts_dir).mkdir(parents=True, exist_ok=True)

# 展开 postx 配置文件路径（非空时展开 ~）
if settings.postx_config_path:
    settings.postx_config_path = str(
        Path(settings.postx_config_path).expanduser()
    )
