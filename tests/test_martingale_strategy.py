"""测试 MartingaleStrategy.execute() 方法。

TDD 第二轮：先写策略测试
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trading_service.exchange import MockExchange
from trading_service.pickers import StaticListSymbolPicker
from trading_service.strategies.martingale import MartingaleConfig, MartingaleStrategy
from trading_service.types import OrderType, TradeDirection


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    repo = InMemoryTradingRepository()
    return MockExchange(repo)
class TestMartingaleExecute:
    """测试马丁格尔策略执行逻辑。"""

    @pytest.mark.asyncio
    async def test_execute_opens_first_position_when_empty(self, exchange: MockExchange) -> None:
        """当没有持仓时，策略应该开第一个仓位。"""
        # ARRANGE
        config = MartingaleConfig(max_positions=1, base_order_size=100.0)
        symbol_picker = StaticListSymbolPicker(["BTCUSDT"])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # Mock fetch_prices 返回价格
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 50000.0})  # type: ignore

        # ACT
        await strategy.execute()

        # ASSERT
        positions = exchange.get_positions(tag="martingale")
        assert len(positions) == 1, "应该开一个仓位"
        assert positions[0].symbol == "BTCUSDT"
        assert positions[0].total_size == 100.0

    @pytest.mark.asyncio
    async def test_execute_respects_max_positions(self, exchange: MockExchange) -> None:
        """策略不应该超过 max_positions 限制。"""
        # ARRANGE - 先开 2 个仓位
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="existing",
        )
        exchange.open_position(
            symbol="ETHUSDT", direction=TradeDirection.LONG,
            size=100, price=3000, tag="martingale", reason_text="existing",
        )

        config = MartingaleConfig(max_positions=2, base_order_size=100.0)
        symbol_picker = StaticListSymbolPicker(["SOLUSDT"])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)
        exchange.fetch_prices = AsyncMock(return_value={"SOLUSDT": 100.0})  # type: ignore

        # ACT
        await strategy.execute()

        # ASSERT - 仍然只有 2 个持仓，没有新开
        positions = exchange.get_positions(tag="martingale")
        assert len(positions) == 2, "不应该超过 max_positions 限制"

    @pytest.mark.asyncio
    async def test_exclude_existing_symbols(self, exchange: MockExchange) -> None:
        """已有持仓的币种不应该重复开仓。"""
        # ARRANGE - BTCUSDT 已有持仓
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="existing",
        )

        config = MartingaleConfig(max_positions=5, base_order_size=100.0)
        symbol_picker = StaticListSymbolPicker(["BTCUSDT", "ETHUSDT"])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 50000.0, "ETHUSDT": 3000.0})  # type: ignore

        # ACT
        await strategy.execute()

        # ASSERT - 只新开了 ETHUSDT，没有重复开 BTCUSDT
        positions = exchange.get_positions(tag="martingale")
        symbols = {p.symbol for p in positions}
        assert len(positions) == 2
        assert "ETHUSDT" in symbols, "应该新开 ETHUSDT 仓位"


class TestMartingaleAddPosition:
    """测试马丁格尔加仓逻辑。"""

    @pytest.mark.asyncio
    async def test_add_position_when_price_drops(self, exchange: MockExchange) -> None:
        """价格下跌到安全订单触发点时，应该加仓。"""
        # ARRANGE - 开初始仓位，价格 50000
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(
            max_positions=1,
            base_order_size=100.0,
            safety_order_count=3,
            safety_order_step_scale=1.5,  # 每 1.5% 下跌加仓
            safety_order_volume_scale=2.0,  # 加仓量翻倍
        )
        symbol_picker = StaticListSymbolPicker([])  # 没有新币种
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格下跌 2%，触发加仓
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 49000.0})  # 下跌 2%

        # ACT
        await strategy.execute()

        # ASSERT - 应该有 2 个订单（1 个初始 + 1 个加仓）
        position = exchange.get_positions(tag="martingale")[0]
        add_orders = [o for o in position.orders if o.order_type.value == "ADD"]
        assert len(add_orders) == 1, f"应该有 1 个加仓订单，实际有 {len(add_orders)}"
        assert add_orders[0].size == 200.0, "加仓量应该是 base_order_size * volume_scale"

    @pytest.mark.asyncio
    async def test_respect_safety_order_count_limit(self, exchange: MockExchange) -> None:
        """不应该超过 safety_order_count 限制。"""
        # ARRANGE - 已有 3 个加仓订单
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )
        # 手动添加 3 个加仓订单
        for i in range(3):
            from trading_service.repository import OrderRecord
            from trading_service.types import OrderType
            exchange.db.save_order(OrderRecord(
                id=exchange._new_id(),
                position_id=position.id,
                symbol="BTCUSDT",
                direction="long",
                size=200 * (2 ** i),
                price=50000 * (1 - 0.015 * (i + 1)),
                order_type=OrderType.ADD.value,
            ))

        config = MartingaleConfig(max_positions=1, safety_order_count=3)
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 45000.0})

        # ACT
        await strategy.execute()

        # ASSERT - 仍然只有 3 个加仓订单
        position = exchange.get_positions(tag="martingale")[0]
        add_orders = [o for o in position.orders if o.order_type.value == "ADD"]
        assert len(add_orders) == 3, "不应该超过 safety_order_count 限制"


class TestMartingaleTakeProfit:
    """测试马丁格尔止盈平仓逻辑。"""

    @pytest.mark.asyncio
    async def test_close_when_price_reaches_take_profit(self, exchange: MockExchange) -> None:
        """价格上涨达到止盈目标时，应该自动平仓。"""
        # ARRANGE - 开仓价格 50000
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(
            max_positions=1,
            base_order_size=100.0,
            take_profit_pct=1.5,  # 1.5% 止盈
        )
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格上涨 2%，触发止盈
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 51000.0})

        # ACT
        await strategy.execute()

        # ASSERT - 持仓已平仓
        positions = exchange.get_positions(tag="martingale")
        assert len(positions) == 1
        assert positions[0].status == "closed", f"应该已平仓，但状态是 {positions[0].status}"
        assert positions[0].exit_price == 51000.0

    @pytest.mark.asyncio
    async def test_no_close_below_take_profit(self, exchange: MockExchange) -> None:
        """价格未达到止盈目标时，不应平仓。"""
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(max_positions=1, take_profit_pct=2.0)
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 只上涨 1%，未达到止盈目标
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 50500.0})

        # ACT
        await strategy.execute()

        # ASSERT - 持仓仍为 open
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "open"

    @pytest.mark.asyncio
    async def test_take_profit_after_multiple_adds(self, exchange: MockExchange) -> None:
        """多次加仓后，止盈目标基于加权平均成本。"""
        # ARRANGE - 初始开仓 + 加仓
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )
        # 加仓后加权均价 = 49333.33
        exchange.add_position(
            position_id=position.id, size=200, price=49000, reason_text="safety_order_1",
        )

        config = MartingaleConfig(max_positions=1, take_profit_pct=1.5)
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格从 49000 回升到 50100（相对于均价 49333，上涨约 1.55%）
        target_price = 49333.33 * 1.0155
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": target_price})

        # ACT
        await strategy.execute()

        # ASSERT - 应该已平仓
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "closed"


class TestMartingaleStopLoss:
    """测试马丁格尔止损平仓逻辑。"""

    @pytest.mark.asyncio
    async def test_stop_loss_when_price_drops_too_much(self, exchange: MockExchange) -> None:
        """价格下跌达到止损线时，应该止损平仓。"""
        # ARRANGE - 开仓价格 50000
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(
            max_positions=1,
            base_order_size=100.0,
            stop_loss_pct=5.0,  # 5% 止损
        )
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格下跌 6%，触发止损
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 47000.0})

        # ACT
        await strategy.execute()

        # ASSERT - 持仓已平仓
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "closed"
        assert positions[0].exit_price == 47000.0

    @pytest.mark.asyncio
    async def test_no_stop_loss_above_threshold(self, exchange: MockExchange) -> None:
        """价格未达到止损线时，不应平仓。"""
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(max_positions=1, stop_loss_pct=5.0)
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 只下跌 4%，未到止损线
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 48000.0})

        # ACT
        await strategy.execute()

        # ASSERT - 持仓仍为 open
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "open"

    @pytest.mark.asyncio
    async def test_stop_loss_takes_priority_over_add(self, exchange: MockExchange) -> None:
        """止损优先级高于加仓 - 达到止损线时直接平仓，不加仓。"""
        # ARRANGE
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )

        config = MartingaleConfig(
            max_positions=1,
            base_order_size=100.0,
            safety_order_count=3,
            safety_order_step_scale=1.5,  # 1.5% 加仓
            stop_loss_pct=3.0,  # 3% 止损
        )
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格下跌 4% - 既达到加仓线也达到止损线
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": 48000.0})

        # ACT
        await strategy.execute()

        # ASSERT - 应该已平仓（止损优先），不应该有加仓订单
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "closed", "应该止损平仓"

        orders = exchange.db.get_orders_by_position(positions[0].id)
        add_orders = [o for o in orders if o.order_type == OrderType.ADD.value]
        assert len(add_orders) == 0, "止损后不应该有加仓订单"

    @pytest.mark.asyncio
    async def test_stop_loss_after_multiple_adds(self, exchange: MockExchange) -> None:
        """多次加仓后，止损基于加权平均成本计算。"""
        # ARRANGE - 初始开仓 + 一次加仓
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="initial",
        )
        # 加仓后加权均价 = 49333.33
        exchange.add_position(
            position_id=position.id, size=200, price=49000, reason_text="safety_order_1",
        )

        config = MartingaleConfig(max_positions=1, stop_loss_pct=3.0)
        symbol_picker = StaticListSymbolPicker([])
        strategy = MartingaleStrategy(exchange, config, symbol_picker)

        # 价格相对于均价下跌 4%（达到止损线）
        stop_price = 49333.33 * 0.96  # 下跌 4%
        exchange.fetch_prices = AsyncMock(return_value={"BTCUSDT": stop_price})

        # ACT
        await strategy.execute()

        # ASSERT - 应该已平仓
        positions = exchange.get_positions(tag="martingale")
        assert positions[0].status == "closed"
