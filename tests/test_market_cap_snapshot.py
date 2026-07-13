"""测试 market_cap 快照存储（TDD 红阶段）。

开仓时把选币算出的合约市值快照存入 Position，定格不变，供前端展示。
数据流：选币(SymbolInfo.market_cap) -> 信号 metadata -> open_position(market_cap=...) -> Position 持久化。

覆盖场景：
1. open_position 接收 market_cap 并存入 Position
2. Position round-trip（to_record/from_record 保留 market_cap）
3. _open_from_signals 从信号 metadata 取 market_cap 传给 open_position
4. 默认值 0.0 向后兼容（旧调用/martingale 不传 market_cap）
"""
from __future__ import annotations

from trading_service.exchange import MockExchange, Position
from trading_service.types import TradeDirection


class TestPositionMarketCapField:
    """Position 领域对象的 market_cap 字段与 round-trip。"""

    def test_position_has_market_cap_field_default_zero(self) -> None:
        """空值：Position.market_cap 默认 0.0（向后兼容旧持仓）。"""
        pos = Position(
            id="p1",
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            entry_price=50000.0,
            total_size=1.0,
        )
        assert pos.market_cap == 0.0, "market_cap 默认应为 0.0"

    def test_position_round_trip_preserves_market_cap(self) -> None:
        """幂等性：to_record/from_record 往返应保留 market_cap。"""
        pos = Position(
            id="p1",
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            entry_price=50000.0,
            total_size=1.0,
            market_cap=48_200_000.0,
        )
        record = pos.to_record()
        assert record.market_cap == 48_200_000.0, "to_record 应携带 market_cap"

        restored = Position.from_record(record)
        assert restored.market_cap == 48_200_000.0, \
            f"from_record 应恢复 market_cap，实际 {restored.market_cap}"


class TestOpenPositionMarketCapSnapshot:
    """open_position 接收并持久化 market_cap 快照。"""

    def test_open_position_stores_market_cap(self, exchange: MockExchange) -> None:
        """正常路径：开仓传入 market_cap -> 持久化 -> 读取一致。"""
        position = exchange.open_position(
            symbol="ABCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=3.0,
            tag="micro_cap",
            reason_text="金叉信号开仓",
            market_cap=30_000_000.0,
        )

        assert position.market_cap == 30_000_000.0, "返回的 Position 应携带 market_cap"

        # 从 DB 读回验证持久化
        restored = exchange.get_position(position.id)
        assert restored is not None
        assert restored.market_cap == 30_000_000.0, \
            f"持久化的 market_cap 应为 3000万，实际 {restored.market_cap}"

    def test_open_position_default_market_cap_zero(self, exchange: MockExchange) -> None:
        """向后兼容：不传 market_cap -> 默认 0.0（martingale 等现有调用不破坏）。"""
        position = exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason_text="策略信号开仓",
        )

        assert position.market_cap == 0.0, "不传 market_cap 应默认 0.0"

    def test_market_cap_snapshot_does_not_change_on_add(
        self, exchange: MockExchange
    ) -> None:
        """幂等性：加仓不应改变 market_cap 快照（开仓时定格）。"""
        position = exchange.open_position(
            symbol="ABCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=3.0,
            tag="micro_cap",
            reason_text="开仓",
            market_cap=30_000_000.0,
        )

        exchange.add_position(position.id, size=100.0, price=2.5, reason_text="加仓")

        restored = exchange.get_position(position.id)
        assert restored is not None
        assert restored.market_cap == 30_000_000.0, \
            "加仓不应改变 market_cap 快照，应在开仓时定格"


class TestGetPositionContextMarketCap:
    """get_position_context（详情 API 响应）应返回 market_cap。"""

    def test_context_includes_market_cap(self, exchange: MockExchange) -> None:
        """正常路径：详情 context 含 market_cap 字段。"""
        position = exchange.open_position(
            symbol="ABCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=3.0,
            tag="micro_cap",
            reason_text="开仓",
            market_cap=30_000_000.0,
        )

        context = exchange.get_position_context(position.id)
        assert context is not None
        assert context["market_cap"] == 30_000_000.0, \
            f"详情 context 应含 market_cap，实际 {context.get('market_cap')}"
