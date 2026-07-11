from __future__ import annotations
from typing import Any

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker


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
