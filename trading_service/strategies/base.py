from __future__ import annotations
from typing import Any

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.strategies.symbol_picker import ISymbolPicker


@dataclass
class StrategyConfig:
    """策略配置基类。"""


class Strategy(ABC):
    """策略基类。"""

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
    async def execute(self) -> None:
        """执行策略。"""

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
