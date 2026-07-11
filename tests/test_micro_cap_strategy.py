"""测试 MicroCapStrategy 信号驱动入场逻辑。

策略逻辑（重构后）：
1. 从数据库拉取 golden_cross 信号（由信号检测器产出）
2. 排除已持仓 symbol
3. 每笔买入 position_size_usdt（默认 10 USDT）
4. 动作记录关联 signal_ids

测试覆盖：正常路径、边界、隔离、空值、signal_ids 关联。
全部使用内存实现，零网络、毫秒级运行。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.repository import SignalRecord
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
from trading_service.types import TradeDirection


class FakeMicroCapPicker(ISymbolPicker):
    """内存版选币器 - micro_cap 策略不再使用 picker 做信号过滤，但基类仍需要。"""

    async def pick(self) -> list[SymbolInfo]:
        return []


def make_signal(
    symbol: str,
    signal_type: str = "golden_cross",
    direction: str = "bullish",
    severity: int = 3,
) -> SignalRecord:
    """构造一条信号记录。"""
    return SignalRecord(
        id=f"sig_{symbol}",
        symbol=symbol,
        signal_type=signal_type,
        direction=direction,
        severity=severity,
        description=f"{symbol} 金叉信号",
    )


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository

    repo = InMemoryTradingRepository()
    return MockExchange(repo)


@pytest.fixture
def strategy(exchange: MockExchange) -> MicroCapStrategy:
    """创建 micro_cap 策略实例。"""
    config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
    return MicroCapStrategy(exchange, config, FakeMicroCapPicker())


class TestMicroCapSignalConsumption:
    """测试信号驱动入场。"""

    @pytest.mark.asyncio
    async def test_opens_position_on_golden_cross_signal(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """正常路径：DB 中有金叉信号 -> 开仓。"""
        exchange.db.save_signal(make_signal("ABCUSDT"))
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1, "应该开一个仓位"
        assert positions[0].symbol == "ABCUSDT"
        assert positions[0].total_size == 10.0
        assert positions[0].direction == TradeDirection.LONG

    @pytest.mark.asyncio
    async def test_no_open_without_signals(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """空值：DB 中无信号时不开仓。"""
        exchange.fetch_prices = AsyncMock(return_value={})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0, "无信号不应开仓"

    @pytest.mark.asyncio
    async def test_ignores_non_golden_signals(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """信号过滤：死叉/横盘信号不触发开仓（策略只消费金叉）。"""
        exchange.db.save_signal(make_signal("AAAUSDT", signal_type="dead_cross", direction="bearish"))
        exchange.db.save_signal(make_signal("BBBUSDT", signal_type="sideways_bottom", direction="neutral"))
        exchange.fetch_prices = AsyncMock(return_value={"AAAUSDT": 1.0, "BBBUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0, "非金叉信号不应开仓"

    @pytest.mark.asyncio
    async def test_respects_max_positions(
        self, exchange: MockExchange
    ) -> None:
        """边界：已有 max_positions 个持仓时不再开仓。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        exchange.open_position(
            symbol="BBBUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )

        config = MicroCapConfig(max_positions=2, position_size_usdt=10.0)
        strategy = MicroCapStrategy(exchange, config, FakeMicroCapPicker())
        exchange.db.save_signal(make_signal("CCCUSDT"))
        exchange.fetch_prices = AsyncMock(return_value={"CCCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "不应该超过 max_positions"
        symbols = {p.symbol for p in positions}
        assert "CCCUSDT" not in symbols, "满了不应再开新仓"

    @pytest.mark.asyncio
    async def test_skip_existing_symbols(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """隔离：已有持仓的 symbol 不重复开仓。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        # 同一 symbol 有金叉信号，但已持仓
        exchange.db.save_signal(make_signal("AAAUSDT"))
        # 新 symbol 有金叉信号
        exchange.db.save_signal(make_signal("BBBUSDT"))
        exchange.fetch_prices = AsyncMock(return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "应有 2 个仓位（1 旧 + 1 新）"
        symbols = {p.symbol for p in positions}
        assert "BBBUSDT" in symbols, "应该新开 BBBUSDT"

    @pytest.mark.asyncio
    async def test_action_record_links_signal_ids(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """动作记录的 signal_ids 应关联到消费的信号。"""
        signal = make_signal("ABCUSDT")
        exchange.db.save_signal(signal)
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1
        actions = exchange.db.list_actions_by_position(positions[0].id)
        assert len(actions) == 1
        assert signal.id in actions[0].signal_ids, "动作记录应关联信号 ID"

    @pytest.mark.asyncio
    async def test_open_multiple_within_quota(
        self, exchange: MockExchange
    ) -> None:
        """混合场景：多个金叉信号按配额开仓。"""
        config = MicroCapConfig(max_positions=3, position_size_usdt=10.0)
        strategy = MicroCapStrategy(exchange, config, FakeMicroCapPicker())
        exchange.db.save_signal(make_signal("AAAUSDT"))
        exchange.db.save_signal(make_signal("BBBUSDT"))
        exchange.db.save_signal(make_signal("CCCUSDT"))
        exchange.fetch_prices = AsyncMock(  # type: ignore
            return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0, "CCCUSDT": 3.0}
        )

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 3, "应该在配额内开 3 个仓位"
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAAUSDT", "BBBUSDT", "CCCUSDT"}

    @pytest.mark.asyncio
    async def test_tag_isolation_from_martingale(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """隔离机制：micro_cap 开仓不影响 martingale 持仓。"""
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="martingale_entry",
        )
        exchange.db.save_signal(make_signal("ABCUSDT"))
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        micro_positions = exchange.get_positions(tag="micro_cap")
        mart_positions = exchange.get_positions(tag="martingale")
        assert len(micro_positions) == 1, "micro_cap 应开 1 仓"
        assert len(mart_positions) == 1, "martingale 持仓应保持不变"

    @pytest.mark.asyncio
    async def test_idempotent_no_duplicate_on_re_execute(
        self, exchange: MockExchange, strategy: MicroCapStrategy
    ) -> None:
        """幂等：同一信号被多轮策略看到不会重复开仓。"""
        exchange.db.save_signal(make_signal("ABCUSDT"))
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()
        await strategy.execute()  # 第二轮，同一信号仍在 DB 中

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1, "同一信号不应导致重复开仓"


class TestMicroCapStatus:
    """测试状态报告。"""

    def test_get_status_returns_config_and_counts(
        self, exchange: MockExchange
    ) -> None:
        """get_status 应返回配置和持仓统计。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="entry",
        )
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(max_positions=5, position_size_usdt=10.0),
            FakeMicroCapPicker(),
        )

        status = strategy.get_status()

        assert status["config"]["max_positions"] == 5
        assert status["open_positions"] == 1
        assert status["total_positions"] == 1

    def test_get_status_empty(self, exchange: MockExchange) -> None:
        """空值：无持仓时状态正确。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker(),
        )

        status = strategy.get_status()

        assert status["open_positions"] == 0
        assert status["total_positions"] == 0
