"""贴文记录模型"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_service.repository.models.base import Base


class PostModel(Base):
    """贴文记录模型 -- 内容层，LLM 生成的社交媒体贴文及其 prompt。

    通过 execution_id 关联策略执行轮次，与 StrategyActionModel 同级。
    一次执行可能产多篇贴文（交易型按 symbol 分组），一对多关系。
    """

    __tablename__ = "trading_posts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    style: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    post_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
