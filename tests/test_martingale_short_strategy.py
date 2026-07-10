"""测试马丁做空策略（MartingaleShortStrategy）。

验证做空方向、涨幅加仓、tag 隔离等核心逻辑。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trading_service.exchange import MockExchange
from trading_service.pickers import StaticListSymbolPicker
from trading_service.strategies.martingale import MartingaleConfig
from trading_service.strategies.martingale_short import MartingaleShortStrategy
from trading_service.types import OrderType, TradeDirection


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    repo = InMemoryTradingRepository()
    return MockExchange(repo)


class TestMartingaleShortExecute:
    """测试做空马丁策略执行逻辑。"""

    @pytest.mark.asyncio
    async def test_opens_short_position_when_empty(self, exchange: MockExchange) -> None:
        """做空策略应开 SHORT 仓位。"""
        config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
        )
        strategy = MartingaleShortStrategy(
            exchange, config, StaticListSymbolPicker(["BTCUSDT"])
        )
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 50000.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale_short")
        assert len(positions) == 1
        assert positions[0].direction == TradeDirection.SHORT, "应该是做空方向"
        assert positions[0].tag == "martingale_short"

    @pytest.mark.asyncio
    async def test_add_position_when_price_rises(self, exchange: MockExchange) -> None:
        """做空时价格上涨（亏损方向）应触发加仓。"""
        config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
            safety_order_count=3,
            safety_order_step_scale=1.5,
        )
        strategy = MartingaleShortStrategy(
            exchange, config, StaticListSymbolPicker(["BTCUSDT"])
        )

        # 先开空仓 @ 50000
        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.SHORT,
            size=100.0,
            price=50000.0,
            tag="martingale_short",
            reason="initial",
        )

        # 价格上涨 3%（超过第1次加仓阈值 1.5%）
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 51500.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale_short")
        assert len(positions) == 1
        orders = positions[0].orders
        add_orders = [o for o in orders if o.order_type == OrderType.ADD]
        assert len(add_orders) == 1, "应有 1 个加仓订单"

    @pytest.mark.asyncio
    async def test_no_add_when_price_drops(self, exchange: MockExchange) -> None:
        """做空时价格下跌（盈利方向）不应加仓。"""
        config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
            safety_order_count=3,
        )
        strategy = MartingaleShortStrategy(
            exchange, config, StaticListSymbolPicker(["BTCUSDT"])
        )

        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.SHORT,
            size=100.0,
            price=50000.0,
            tag="martingale_short",
            reason="initial",
        )

        # 价格下跌 5%（盈利方向）
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 47500.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale_short")
        add_orders = [o for o in positions[0].orders if o.order_type == OrderType.ADD]
        assert len(add_orders) == 0, "价格下跌不应加仓"

    @pytest.mark.asyncio
    async def test_take_profit_when_price_drops(self, exchange: MockExchange) -> None:
        """做空时价格下跌到止盈点应平仓。"""
        config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
            take_profit_pct=2.0,
        )
        strategy = MartingaleShortStrategy(
            exchange, config, StaticListSymbolPicker(["BTCUSDT"])
        )

        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.SHORT,
            size=100.0,
            price=50000.0,
            tag="martingale_short",
            reason="initial",
        )

        # 价格下跌 2.5%（达到止盈 2%）
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 48750.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale_short")
        assert len(positions) == 1
        assert positions[0].status == "closed", "应该已平仓止盈"

    @pytest.mark.asyncio
    async def test_stop_loss_when_price_rises_too_much(self, exchange: MockExchange) -> None:
        """做空时价格上涨到止损点应平仓。"""
        config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
            stop_loss_pct=10.0,
            safety_order_count=0,  # 禁止加仓，直接测止损
        )
        strategy = MartingaleShortStrategy(
            exchange, config, StaticListSymbolPicker(["BTCUSDT"])
        )

        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.SHORT,
            size=100.0,
            price=50000.0,
            tag="martingale_short",
            reason="initial",
        )

        # 价格上涨 12%（超过止损 10%）
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 56000.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="martingale_short")
        assert positions[0].status == "closed", "应该已止损平仓"

    @pytest.mark.asyncio
    async def test_tag_isolation_from_long_martingale(self, exchange: MockExchange) -> None:
        """做空马丁的持仓不应影响做多马丁。"""
        # 做多马丁开仓
        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason="long_entry",
        )

        short_config = MartingaleConfig(
            direction=TradeDirection.SHORT,
            max_positions=1,
            base_order_size=100.0,
        )
        short_strategy = MartingaleShortStrategy(
            exchange, short_config, StaticListSymbolPicker(["ETHUSDT"])
        )
        exchange.fetch_prices = AsyncMock(return_value={"ETHUSDT": 3000.0})  # type: ignore

        await short_strategy.execute()

        # 做多马丁持仓不受影响
        long_positions = exchange.get_positions(tag="martingale")
        assert len(long_positions) == 1
        assert long_positions[0].direction == TradeDirection.LONG

        # 做空马丁有独立持仓
        short_positions = exchange.get_positions(tag="martingale_short")
        assert len(short_positions) == 1
        assert short_positions[0].direction == TradeDirection.SHORT
