from __future__ import annotations
from typing import Any

from trading_service.exchange import MockExchange, Position
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.pickers import ISymbolPicker
from trading_service.types import OrderType, TradeDirection


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
    direction: TradeDirection = TradeDirection.LONG


class MartingaleStrategy(Strategy):
    """马丁格尔策略。"""

    name = "martingale"
    cron = "*/30 * * * * *"  # 6字段：秒 分 时 日 月 周 = 每30秒

    def __init__(
        self,
        exchange: MockExchange,
        config: MartingaleConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        super().__init__(exchange, config, symbol_picker)
        self.config: MartingaleConfig = config

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行策略。

        优先级：止损 -> 止盈 -> 加仓 -> 开新仓
        返回执行的动作列表。
        """
        actions: list[StrategyAction] = []
        positions = self.exchange.get_positions(tag=self.name, status="open")
        current_position_count = len(positions)

        if positions:
            symbols = [p.symbol for p in positions]
            prices = await self.exchange.fetch_prices(symbols)
            for position in positions:
                current_price = prices.get(position.symbol, 0.0)
                if current_price > 0:
                    # 1. 先检查止损 - 最高优先级
                    if self._check_stop_loss(position, current_price, execution_id):
                        actions.append(StrategyAction(
                            type="close",
                            symbol=position.symbol,
                            reason=f"止损平仓 @ {current_price}",
                        ))
                        continue  # 已平仓，跳过后续检查
                    # 2. 再检查止盈
                    if self._check_take_profit(position, current_price, execution_id):
                        actions.append(StrategyAction(
                            type="close",
                            symbol=position.symbol,
                            reason=f"止盈平仓 @ {current_price}",
                        ))
                        continue
                    # 3. 最后检查加仓
                    add_action = self._check_and_add(position, current_price, execution_id)
                    if add_action:
                        actions.append(add_action)

        if current_position_count < self.config.max_positions:
            actions.extend(await self._open_new_positions(current_position_count, execution_id))

        return actions

    def _check_stop_loss(self, position: Position, current_price: float, execution_id: str = "") -> bool:
        """检查是否应该止损平仓。返回 True 表示已平仓。"""
        loss_pct = -position.pnl_pct(current_price)  # pnl_pct 负数表示亏损，转成正数
        if loss_pct >= self.config.stop_loss_pct:
            self.exchange.close_position(
                position_id=position.id,
                price=current_price,
                reason_text=f"止损平仓 @ {current_price}",
                reason_data={
                    "action": "stop_loss",
                    "price": current_price,
                    "loss_pct": round(loss_pct, 2),
                },
                execution_id=execution_id,
            )
            return True
        return False

    def _check_take_profit(self, position: Position, current_price: float, execution_id: str = "") -> bool:
        """检查是否应该止盈平仓。返回 True 表示已平仓。"""
        profit_pct = position.pnl_pct(current_price)
        if profit_pct >= self.config.take_profit_pct:
            self.exchange.close_position(
                position_id=position.id,
                price=current_price,
                reason_text=f"止盈平仓 @ {current_price}",
                reason_data={
                    "action": "take_profit",
                    "price": current_price,
                    "profit_pct": round(profit_pct, 2),
                },
                execution_id=execution_id,
            )
            return True
        return False

    async def _open_new_positions(self, current_count: int, execution_id: str = "") -> list[StrategyAction]:
        """开新仓位逻辑。"""
        actions: list[StrategyAction] = []
        symbol_infos = await self.symbol_picker.pick()
        positions = self.exchange.get_positions(tag=self.name, status="open")
        occupied_symbols = {p.symbol for p in positions}
        available_infos = [s for s in symbol_infos if s.symbol not in occupied_symbols]

        if not available_infos:
            return actions

        symbols = [s.symbol for s in available_infos]
        prices = await self.exchange.fetch_prices(symbols)
        slots_remaining = self.config.max_positions - current_count
        infos_to_open = available_infos[:slots_remaining]

        for info in infos_to_open:
            price = prices.get(info.symbol, 0.0)
            if price > 0:
                self.exchange.open_position(
                    symbol=info.symbol,
                    direction=self.config.direction,
                    size=self.config.base_order_size,
                    price=price,
                    tag=self.name,
                    reason_text=f"开仓 @ {price}",
                    reason_data={
                        "action": "initial_entry",
                        "price": price,
                        "size": self.config.base_order_size,
                    },
                    execution_id=execution_id,
                )
                actions.append(StrategyAction(
                    type="open",
                    symbol=info.symbol,
                    reason=f"开仓 @ {price}",
                ))
        return actions

    def _check_and_add(self, position: Position, current_price: float, execution_id: str = "") -> StrategyAction | None:
        """检查是否应该加仓，如果需要则执行加仓。返回动作记录或 None。

        做多：价格下跌到 entry*(1-drop_pct) 以下时加仓（跌幅加仓）。
        做空：价格上涨到 entry*(1+rise_pct) 以上时加仓（涨幅加仓）。
        """
        add_orders = [o for o in position.orders if o.order_type == OrderType.ADD]
        add_count = len(add_orders)

        if add_count >= self.config.safety_order_count:
            return None

        add_target_count = add_count + 1
        step_pct = self.config.safety_order_step_scale * add_target_count / 100

        if self.config.direction == TradeDirection.LONG:
            # 做多：价格下跌触发加仓
            trigger_price = position.entry_price * (1 - step_pct)
            should_add = current_price <= trigger_price
        else:
            # 做空：价格上涨触发加仓
            trigger_price = position.entry_price * (1 + step_pct)
            should_add = current_price >= trigger_price

        if should_add:
            add_size = self.config.base_order_size * (self.config.safety_order_volume_scale ** (add_count + 1))

            self.exchange.add_position(
                position_id=position.id,
                size=add_size,
                price=current_price,
                reason_text=f"第 {add_target_count} 次加仓 @ {current_price}",
                reason_data={
                    "action": "safety_order",
                    "layer": add_target_count,
                    "price": current_price,
                    "size": add_size,
                },
                execution_id=execution_id,
            )
            return StrategyAction(
                type="add",
                symbol=position.symbol,
                reason=f"第 {add_target_count} 次加仓 @ {current_price}",
            )
        return None

    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
        positions = self.exchange.get_positions(tag=self.name)
        return {
            "config": {
                "max_positions": self.config.max_positions,
                "base_order_size": self.config.base_order_size,
                "safety_order_count": self.config.safety_order_count,
                "safety_order_step_scale": self.config.safety_order_step_scale,
                "safety_order_volume_scale": self.config.safety_order_volume_scale,
                "take_profit_pct": self.config.take_profit_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
            },
            "open_positions": len([p for p in positions if p.status == "open"]),
            "total_positions": len(positions),
        }
