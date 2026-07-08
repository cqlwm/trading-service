from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine


def get_current_revision(db_url: str) -> str | None:
    """获取数据库的当前版本。"""
    engine = create_engine(db_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def get_head_revision() -> str | None:
    """获取代码的最新版本。"""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    return script.get_current_head()


def check_migrations(db_path: str) -> tuple[bool, str | None, str | None]:
    """检查数据库迁移是否是最新的。

    Returns:
        (is_latest, current_rev, head_rev)
    """
    db_url = f"sqlite:///{Path(db_path).expanduser()}"
    current_rev = get_current_revision(db_url)
    head_rev = get_head_revision()

    # 如果数据库是全新的（current_rev 是 None），也需要迁移
    return current_rev == head_rev, current_rev or "None", head_rev


def run_migrations(db_path: str) -> None:
    """运行所有未执行的迁移。"""
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    # 覆盖数据库路径
    db_url = f"sqlite:///{Path(db_path).expanduser()}"
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(alembic_cfg, "head")
