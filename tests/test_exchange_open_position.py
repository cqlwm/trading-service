"""测试 MockExchange.open_position 方法。

TDD 第一步：先写测试，再实现功能
"""
from __future__ import annotations

from trading_service.exchange import MockExchange
from trading_service.repository import OrderRecord
from trading_service.types import OrderType, TradeDirection


class TestOpenPosition:
    """测试开仓功能。"""

    def test_open_position_creates_position_record(self, exchange: MockExchange) -> None:
        """开仓应该创建一条 position 记录。"""
        position = exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason="strategy_signal",
        )

        assert position is not None
        assert position.id is not None
        assert position.symbol == "BTCUSDT"
        assert position.direction == TradeDirection.LONG
        assert position.total_size == 100.0
        assert position.entry_price == 50000.0
        assert position.tag == "martingale"
        assert position.status == "open"

    def test_open_position_creates_open_order(self, exchange: MockExchange) -> None:
        """开仓应该同时创建一条 OPEN 类型的订单。"""
        position = exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason="strategy_signal",
        )

        orders = exchange.db.get_orders_by_position(position.id)
        assert len(orders) == 1
        order = orders[0]
        assert order.order_type == OrderType.OPEN.value
        assert order.symbol == "BTCUSDT"
        assert order.size == 100.0
        assert order.price == 50000.0
        assert order.reason == "strategy_signal"

    def test_open_position_has_correct_tag_isolation(self, exchange: MockExchange) -> None:
        """开仓后，用 tag 应该能查询到对应持仓。"""
        exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100,
            price=50000,
            tag="martingale",
            reason="test",
        )
        exchange.open_position(
            symbol="ETHUSDT",
            direction=TradeDirection.SHORT,
            size=50,
            price=3000,
            tag="micro_cap",
            reason="test",
        )

        martingale_positions = exchange.get_positions(tag="martingale")
        micro_cap_positions = exchange.get_positions(tag="micro_cap")

        assert len(martingale_positions) == 1
        assert martingale_positions[0].symbol == "BTCUSDT"
        assert len(micro_cap_positions) == 1
        assert micro_cap_positions[0].symbol == "ETHUSDT"


class TestTransactionAtomicity:
    """测试事务原子性 - 要么全部成功，要么全部回滚。"""

    def test_transaction_rollback_on_exception(self, exchange: MockExchange) -> None:
        """事务中途异常时，所有操作应该回滚。"""
        from tests.conftest import InMemoryTradingRepository

        class FailingRepository(InMemoryTradingRepository):
            def save_order(self, order: OrderRecord) -> None:
                raise RuntimeError("模拟数据库写入失败")

        failing_exchange = MockExchange(FailingRepository())

        try:
            failing_exchange.open_position(
                symbol="BTCUSDT",
                direction=TradeDirection.LONG,
                size=100,
                price=50000,
                tag="test",
                reason="test",
            )
        except RuntimeError:
            pass

        positions = failing_exchange.get_positions()
        assert len(positions) == 0, "事务应该回滚，不应该有持仓"


class TestAddPosition:
    """测试加仓功能。"""

    def test_add_position_increases_total_size(self, exchange: MockExchange) -> None:
        """加仓应该增加持仓总数量。"""
        position = exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason="initial",
        )

        updated_position = exchange.add_position(
            position_id=position.id,
            size=200.0,
            price=49000.0,
            reason="safety_order_1",
        )

        assert updated_position.total_size == 300.0
        assert abs(updated_position.entry_price - 49333.333333333336) < 0.01

    def test_add_position_creates_add_order(self, exchange: MockExchange) -> None:
        """加仓应该创建 ADD 类型的订单。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason="initial",
        )

        exchange.add_position(
            position_id=position.id,
            size=200,
            price=49000,
            reason="safety_order_1",
        )

        orders = exchange.db.get_orders_by_position(position.id)
        add_orders = [o for o in orders if o.order_type == OrderType.ADD.value]
        assert len(add_orders) == 1
        assert add_orders[0].reason == "safety_order_1"


class TestClosePosition:
    """测试平仓功能。"""

    def test_close_position_updates_status(self, exchange: MockExchange) -> None:
        """平仓应该将持仓状态改为 closed。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason="initial",
        )

        result = exchange.close_position(
            position_id=position.id,
            price=50750.0,
            reason="take_profit",
        )

        assert result is not None
        updated = exchange.get_position(position.id)
        assert updated is not None
        assert updated.status == "closed"
        assert updated.exit_price == 50750.0

    def test_close_position_creates_close_order(self, exchange: MockExchange) -> None:
        """平仓应该创建 CLOSE 类型的订单。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason="initial",
        )

        exchange.close_position(
            position_id=position.id,
            price=50750.0,
            reason="take_profit",
        )

        orders = exchange.db.get_orders_by_position(position.id)
        close_orders = [o for o in orders if o.order_type == OrderType.CLOSE.value]
        assert len(close_orders) == 1
        assert close_orders[0].reason == "take_profit"

    def test_close_position_returns_pnl(self, exchange: MockExchange) -> None:
        """平仓结果应该包含盈亏信息。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason="initial",
        )

        result = exchange.close_position(
            position_id=position.id,
            price=51000.0,
            reason="take_profit",
        )

        assert result is not None
        assert abs(result.pnl_pct - 2.0) < 0.01
