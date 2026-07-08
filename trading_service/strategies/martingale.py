from __future__ import annotations
from typing import Any

from trading_service.exchange import MockExchange, Position
from trading_service.strategies.base import Strategy, StrategyConfig
from trading_service.pickers import ISymbolPicker
from trading_service.types import TradeDirection, OrderType


from dataclasses import dataclass

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
        """执行策略。
        
        优先级：止损 → 止盈 → 加仓 → 开新仓
        """
        positions = self.exchange.get_positions(tag="martingale", status="open")
        current_position_count = len(positions)

        if positions:
            symbols = [p.symbol for p in positions]
            prices = await self.exchange.fetch_prices(symbols)
            for position in positions:
                current_price = prices.get(position.symbol, 0.0)
                if current_price > 0:
                    # 1. 先检查止损 - 最高优先级
                    if self._check_stop_loss(position, current_price):
                        continue  # 已平仓，跳过后续检查
                    # 2. 再检查止盈
                    if self._check_take_profit(position, current_price):
                        continue
                    # 3. 最后检查加仓
                    self._check_and_add(position, current_price)

        if current_position_count < self.config.max_positions:
            await self._open_new_positions(current_position_count)

    def _check_stop_loss(self, position: Position, current_price: float) -> bool:
        """检查是否应该止损平仓。返回 True 表示已平仓。"""
        loss_pct = -position.pnl_pct(current_price)  # pnl_pct 负数表示亏损，转成正数
        if loss_pct >= self.config.stop_loss_pct:
            self.exchange.close_position(
                position_id=position.id,
                price=current_price,
                reason="stop_loss",
            )
            return True
        return False

    def _check_take_profit(self, position: Position, current_price: float) -> bool:
        """检查是否应该止盈平仓。返回 True 表示已平仓。"""
        profit_pct = position.pnl_pct(current_price)
        if profit_pct >= self.config.take_profit_pct:
            self.exchange.close_position(
                position_id=position.id,
                price=current_price,
                reason="take_profit",
            )
            return True
        return False

    async def _open_new_positions(self, current_count: int) -> None:
        """开新仓位逻辑。"""
        symbol_infos = await self.symbol_picker.pick()
        positions = self.exchange.get_positions(tag="martingale", status="open")
        occupied_symbols = {p.symbol for p in positions}
        available_infos = [s for s in symbol_infos if s.symbol not in occupied_symbols]

        if not available_infos:
            return

        symbols = [s.symbol for s in available_infos]
        prices = await self.exchange.fetch_prices(symbols)
        slots_remaining = self.config.max_positions - current_count
        infos_to_open = available_infos[:slots_remaining]

        for info in infos_to_open:
            price = prices.get(info.symbol, 0.0)
            if price > 0:
                self.exchange.open_position(
                    symbol=info.symbol,
                    direction=TradeDirection.LONG,
                    size=self.config.base_order_size,
                    price=price,
                    tag="martingale",
                    reason="martingale_initial_entry",
                )

    def _check_and_add(self, position: Position, current_price: float) -> None:
        """检查是否应该加仓，如果需要则执行加仓。"""
        add_orders = [o for o in position.orders if o.order_type == OrderType.ADD]
        add_count = len(add_orders)

        if add_count >= self.config.safety_order_count:
            return

        add_target_count = add_count + 1
        drop_pct = self.config.safety_order_step_scale * add_target_count / 100
        trigger_price = position.entry_price * (1 - drop_pct)

        if current_price <= trigger_price:
            add_size = self.config.base_order_size * (self.config.safety_order_volume_scale ** (add_count + 1))

            self.exchange.add_position(
                position_id=position.id,
                size=add_size,
                price=current_price,
                reason=f"safety_order_{add_target_count}",
            )

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
