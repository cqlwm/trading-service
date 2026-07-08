"""
马丁格尔策略模拟演示

演示三种行情场景：
1. 📈 上涨行情 - 快速止盈
2. 📉 下跌行情 - 触发止损
3. 📊 震荡行情 - 先跌后涨，加仓后止盈
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncGenerator

from trading_service.exchange import MockExchange, Position
from tests.conftest import InMemoryTradingRepository
from trading_service.strategies.martingale import MartingaleConfig, MartingaleStrategy
from trading_service.strategies.symbol_picker import ISymbolPicker, SymbolInfo
from trading_service.types import OrderType


@dataclass
class PriceScenario:
    """价格场景。"""
    name: str
    emoji: str
    prices: list[float]


class FixedSymbolPicker(ISymbolPicker):
    """固定返回 BTCUSDT。"""
    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol

    async def pick(self) -> list[SymbolInfo]:
        return [SymbolInfo(
            symbol=self.symbol, price=0.0, volume_24h=0.0,
            market_cap=0.0, price_change_pct_24h=0.0,
        )]


class SimulationExchange(MockExchange):
    """模拟交易所 - 价格可以手动设置。"""
    def __init__(self) -> None:
        super().__init__(InMemoryTradingRepository())
        self.current_prices: dict[str, float] = {}

    async def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        return {s: self.current_prices.get(s, 0.0) for s in symbols}

    def set_price(self, symbol: str, price: float) -> None:
        self.current_prices[symbol] = price


def generate_scenarios() -> list[PriceScenario]:
    """生成三种行情场景。"""
    return [
        PriceScenario(
            name="快速上涨",
            emoji="📈",
            prices=[50000, 50500, 50800, 51000],  # 上涨 2% 止盈
        ),
        PriceScenario(
            name="快速下跌",
            emoji="📉",
            prices=[50000, 49250, 48500, 47500],  # 下跌 5% 止损
        ),
        PriceScenario(
            name="V型反转",
            emoji="✅",
            prices=[50000, 49250, 48500, 49250, 50000, 50750],  # 跌3次加仓，再上涨止盈
        ),
    ]


def print_position_detail(position: Position) -> None:
    """打印持仓详情。"""
    status_icon = "🟢" if position.status == "open" else "🔴"
    print(f"  {status_icon} {position.symbol} | {position.status.upper()}")
    print(f"     均价: ${position.entry_price:,.2f} | 数量: {position.total_size:.2f}")

    orders = position.orders
    for o in orders:
        type_icon = "🎯" if o.order_type == OrderType.OPEN else "📦" if o.order_type == OrderType.ADD else "💰"
        print(f"     {type_icon} {o.order_type.value:5} | ${o.price:,.2f} x {o.size:.2f} | {o.reason}")


async def run_scenario(scenario: PriceScenario) -> None:
    """运行单个场景。"""
    print(f"\n{'='*60}")
    print(f" {scenario.emoji} 场景: {scenario.name}")
    print(f"{'='*60}")

    exchange = SimulationExchange()
    config = MartingaleConfig(
        max_positions=1,
        base_order_size=100.0,
        safety_order_count=3,
        safety_order_step_scale=1.5,  # 每1.5%下跌加仓
        safety_order_volume_scale=2.0,  # 加仓量翻倍
        take_profit_pct=1.5,  # 1.5%止盈
        stop_loss_pct=5.0,  # 5%止损
    )
    symbol_picker = FixedSymbolPicker("BTCUSDT")
    strategy = MartingaleStrategy(exchange, config, symbol_picker)

    for step, price in enumerate(scenario.prices, 1):
        print(f"\n  Step {step}: BTC = ${price:,.2f}")
        exchange.set_price("BTCUSDT", price)

        pnl_display = ""
        if step > 1:
            positions = exchange.get_positions(tag="martingale", status="open")
            if positions:
                pnl = positions[0].pnl_pct(price)
                pnl_display = f" | 盈亏: {pnl:+.2f}%"
        print(f"     价格更新 {pnl_display}")

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale")
        for pos in positions:
            print_position_detail(pos)

    # 最终统计
    print(f"\n  {'-'*50}")
    print("  📊 最终结果:")
    all_positions = exchange.get_positions(tag="martingale")

    if all_positions:
        pos = all_positions[0]
        if pos.status == "closed" and pos.exit_price:
            final_pnl = pos.pnl_pct(pos.exit_price)
            total_cost = pos.entry_price * pos.total_size
            total_value = pos.exit_price * pos.total_size
            pnl_icon = "🟢" if final_pnl >= 0 else "🔴"
            print(f"  {pnl_icon} 平仓盈亏: {final_pnl:+.2f}%")
            print(f"     投入: ${total_cost:,.2f} | 回收: ${total_value:,.2f}")

            orders = exchange.db.get_orders_by_position(pos.id)
            add_count = sum(1 for o in orders if o.order_type == OrderType.ADD.value)
            close_reason = next((o.reason for o in orders if o.order_type == OrderType.CLOSE.value), "unknown")
            print(f"     加仓 {add_count} 次 | 平仓原因: {close_reason}")
        else:
            print(f"  🟡 持仓未平仓 | 均价: ${pos.entry_price:,.2f}")
    else:
        print("  ⚪ 无持仓")


async def main() -> None:
    """运行所有场景。"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                  马丁格尔策略 模拟演示                        ║
╠══════════════════════════════════════════════════════════════╣
║  策略参数:                                                    ║
║    • 初始订单: 100 USD                                       ║
║    • 加仓间距: 每下跌 1.5%                                    ║
║    • 加仓倍率: 2 倍 (每次加仓数量翻倍)                        ║
║    • 最大加仓: 3 次                                          ║
║    • 止盈线: +1.5%                                           ║
║    • 止损线: -5.0%                                           ║
╚══════════════════════════════════════════════════════════════╝
    """)

    scenarios = generate_scenarios()
    for scenario in scenarios:
        await run_scenario(scenario)

    print(f"\n\n{'='*60}")
    print("  💡 关键观察:")
    print("   • V型反转是马丁格尔最赚钱的场景")
    print("   • 加仓摊低了平均成本，小幅度反弹即可止盈")
    print("   • 但要注意资金管理，连续加仓需要足够的保证金")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
