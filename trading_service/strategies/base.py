from __future__ import annotations
from typing import Any

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker
from trading_service.repository import SignalRecord


@dataclass
class StrategyAction:
    """策略执行动作记录，用于 API 响应反馈。"""

    type: str  # "open" | "add" | "close" | "skip"
    symbol: str
    reason: str = ""


@dataclass
class StrategyConfig:
    """策略配置基类。"""


class Strategy(ABC):
    """策略基类。"""

    # 策略标识，用于调度注册和 API 路径（子类必须覆盖）
    name: str = ""
    # cron 表达式（7 字段：秒 分 时 日 月 周 年），空=不参与定时调度
    # 示例："*/30 * * * * *" = 每30秒，"0 * * * * *" = 每分钟
    cron: str = ""

    def __init__(
        self,
        exchange: MockExchange,
        config: StrategyConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        self.exchange = exchange
        self.config = config
        self.symbol_picker = symbol_picker

    @abstractmethod
    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行策略，返回执行的动作列表。

        execution_id 用于将动作记录关联到调度轮次（手动操作为空）。
        """

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""

    def get_recent_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        limit: int = 10,
    ) -> list[SignalRecord]:
        """拉取最近的信号（策略主动消费）。

        信号是市场观察，不是命令。看到同一个信号多次不应导致重复操作，
        策略自身的持仓检查（tag 隔离 + status 过滤）天然防止重复交易。
        """
        return self.exchange.db.list_signals(
            symbol=symbol, signal_type=signal_type, limit=limit,
        )
