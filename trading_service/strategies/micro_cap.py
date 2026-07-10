from __future__ import annotations
from typing import Any

from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.types import CrossSignalType, TradeDirection


@dataclass
class MicroCapConfig(StrategyConfig):
    """微市值策略配置。"""

    max_positions: int = 10
    position_size_usdt: float = 10.0
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 15.0
    min_volume_usdt: float = 1_000_000
    max_market_cap: float = 50_000_000


class MicroCapStrategy(Strategy):
    """微市值做多策略。

    选币（由 SymbolPicker 完成）：市值低于 5000 万、昨日上涨的代币。
    入场：技术分析显示横盘或近期突破（金叉）时，买入 position_size_usdt。
    """

    def __init__(
        self,
        exchange: MockExchange,
        config: MicroCapConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        super().__init__(exchange, config, symbol_picker)
        self.config: MicroCapConfig = config

    async def execute(self) -> list[StrategyAction]:
        """执行策略 - 仅入场逻辑。

        优先级：止盈/止损留待下一轮实现，本轮只做开新仓。
        返回执行的动作列表。
        """
        actions: list[StrategyAction] = []
        positions = self.exchange.get_positions(tag="micro_cap", status="open")
        current_count = len(positions)

        if current_count >= self.config.max_positions:
            return actions

        actions.extend(await self._open_new_positions(current_count))
        return actions

    async def _open_new_positions(self, current_count: int) -> list[StrategyAction]:
        """筛选买入信号并开新仓。"""
        actions: list[StrategyAction] = []
        candidates = await self.symbol_picker.pick()

        occupied = {
            p.symbol for p in self.exchange.get_positions(tag="micro_cap", status="open")
        }
        # 候选 -> 买入信号过滤 -> 排除已持仓
        signals = [
            info for info in candidates
            if info.symbol not in occupied and self._is_buy_signal(info)
        ]

        if not signals:
            return actions

        slots = self.config.max_positions - current_count
        prices = await self.exchange.fetch_prices([s.symbol for s in signals])

        for info in signals[:slots]:
            price = prices.get(info.symbol, 0.0)
            if price > 0:
                self.exchange.open_position(
                    symbol=info.symbol,
                    direction=TradeDirection.LONG,
                    size=self.config.position_size_usdt,
                    price=price,
                    tag="micro_cap",
                    reason=self._entry_reason(info),
                )
                actions.append(StrategyAction(
                    type="open",
                    symbol=info.symbol,
                    detail=f"开仓 @ {price}",
                ))
        return actions

    def _is_buy_signal(self, info: SymbolInfo) -> bool:
        """判定是否为买入信号：横盘或近期金叉突破。"""
        return info.is_sideways_bottom or info.cross_signal == CrossSignalType.GOLDEN

    @staticmethod
    def _entry_reason(info: SymbolInfo) -> str:
        """根据信号类型生成开仓原因，便于审计。"""
        if info.cross_signal == CrossSignalType.GOLDEN:
            return "micro_cap_entry_breakout"
        return "micro_cap_entry_sideways"

    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
        positions = self.exchange.get_positions(tag="micro_cap")
        return {
            "config": {
                "max_positions": self.config.max_positions,
                "position_size_usdt": self.config.position_size_usdt,
                "take_profit_pct": self.config.take_profit_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
                "min_volume_usdt": self.config.min_volume_usdt,
                "max_market_cap": self.config.max_market_cap,
            },
            "open_positions": len([p for p in positions if p.status == "open"]),
            "total_positions": len(positions),
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
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
