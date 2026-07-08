from __future__ import annotations

from trading_service.exchange import MockExchange
from trading_service.strategies.base import Strategy, StrategyConfig
from trading_service.strategies.symbol_picker import ISymbolPicker, SymbolInfo


class MicroCapConfig(StrategyConfig):
    """微市值策略配置。"""

    max_positions: int = 10
    position_size_usdt: float = 50.0
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 15.0
    min_volume_usdt: float = 1_000_000
    max_market_cap: float = 50_000_000


class MicroCapSymbolPicker(ISymbolPicker):
    """微市值币种选择器。"""

    def __init__(
        self,
        min_volume_usdt: float = 1_000_000,
        max_market_cap: float = 50_000_000,
        top_n: int = 20,
    ) -> None:
        self.min_volume_usdt = min_volume_usdt
        self.max_market_cap = max_market_cap
        self.top_n = top_n

    async def pick(self) -> list[SymbolInfo]:
        # TODO: 通过 news-service API 获取真实数据
        return []


class MicroCapStrategy(Strategy):
    """微市值做多策略。"""

    def __init__(
        self,
        exchange: MockExchange,
        config: MicroCapConfig | None = None,
        symbol_picker: ISymbolPicker | None = None,
    ) -> None:
        config = config or MicroCapConfig()
        symbol_picker = symbol_picker or MicroCapSymbolPicker()
        super().__init__(exchange, config, symbol_picker)
        self.config: MicroCapConfig = config

    async def execute(self) -> None:
        """执行策略。"""
        symbols = await self.symbol_picker.pick()
        print(f"MicroCapStrategy.execute: {len(symbols)} symbols")

    def get_status(self) -> dict:
        """获取策略状态。"""
        positions = self.exchange.get_positions(tag="micro_cap")
        return {
            "config": {
                "max_positions": self.config.max_positions,
                "position_size_usdt": self.config.position_size_usdt,
                "take_profit_pct": self.config.take_profit_pct,
            },
            "open_positions": len([p for p in positions if p.status == "open"]),
            "total_positions": len(positions),
        }

    def get_history(self, limit: int = 10) -> list[dict]:
        """获取历史记录。"""
        positions = self.exchange.get_positions(tag="micro_cap")
        return [
            {
                "symbol": p.symbol,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "status": p.status,
                "pnl_pct": p.final_pnl_pct if p.final_pnl_pct else 0.0,
                "created_at": p.created_at.isoformat(),
            }
            for p in positions[:limit]
        ]
