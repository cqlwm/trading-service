from __future__ import annotations
from typing import Any

from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.strategies.base import Strategy, StrategyConfig
from trading_service.strategies.symbol_picker import ISymbolPicker


@dataclass
class MartingaleConfig(StrategyConfig):
    """马丁策略配置。"""

    max_positions: int = 5
    base_order_size: float = 100.0
    safety_order_count: int = 3
    safety_order_step_scale: float = 1.5
    safety_order_volume_scale: float = 2.0
    take_profit_pct: float = 1.5
    stop_loss_pct: float = 20.0


class MartingaleStrategy(Strategy):
    """马丁格尔策略。"""

    def __init__(
        self,
        exchange: MockExchange,
        config: MartingaleConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        super().__init__(exchange, config, symbol_picker)
        self.config: MartingaleConfig = config

    async def execute(self) -> None:
        """执行策略。"""
        # TODO: 实现完整的马丁策略逻辑
        symbols = await self.symbol_picker.pick()
        # 简化实现
        print(f"MartingaleStrategy.execute: {len(symbols)} symbols")

    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
        positions = self.exchange.get_positions(tag="martingale")
        return {
            "config": {
                "max_positions": self.config.max_positions,
                "base_order_size": self.config.base_order_size,
                "safety_order_count": self.config.safety_order_count,
                "take_profit_pct": self.config.take_profit_pct,
            },
            "open_positions": len([p for p in positions if p.status == "open"]),
            "total_positions": len(positions),
        }
