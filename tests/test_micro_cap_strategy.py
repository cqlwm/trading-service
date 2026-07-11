"""测试 MicroCapStrategy 入场逻辑（TDD 红阶段）。

策略逻辑：
1. 市值低于 5000 万、昨日上涨的代币（由 SymbolPicker 预筛）
2. 技术分析：横盘（is_sideways_bottom）或近期突破（cross_signal == "golden"）才买入
3. 每笔买入 position_size_usdt（默认 10 USDT）

测试覆盖 7 类场景：正常路径、边界、隔离、过滤、混合、空值、tag 隔离。
全部使用内存实现，零网络、毫秒级运行。
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
from trading_service.types import CrossSignalType, TradeDirection


class FakeMicroCapPicker(ISymbolPicker):
    """内存版选币器 - 返回带技术分析字段的 SymbolInfo。

    用于测试策略入场逻辑，不依赖任何外部 API。
    """

    def __init__(self, symbols: list[SymbolInfo]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        return list(self.symbols)


def make_info(
    symbol: str,
    price: float = 1.0,
    market_cap: float = 10_000_000.0,
    is_sideways_bottom: bool = False,
    cross_signal: CrossSignalType | None = None,
) -> SymbolInfo:
    """构造一个带技术分析字段的 SymbolInfo。"""
    return SymbolInfo(
        symbol=symbol,
        price=price,
        market_cap=market_cap,
        is_sideways_bottom=is_sideways_bottom,
        cross_signal=cross_signal,
    )


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository

    repo = InMemoryTradingRepository()
    return MockExchange(repo)


class TestMicroCapBuySignal:
    """测试买入信号判定。"""

    def test_sideways_is_buy_signal(self, exchange: MockExchange) -> None:
        """横盘信号应该判定为买入。"""
        config = MicroCapConfig()
        strategy = MicroCapStrategy(
            exchange, config, FakeMicroCapPicker([])
        )
        info = make_info("ABCUSDT", is_sideways_bottom=True)
        assert strategy._is_buy_signal(info) is True, "横盘应为买入信号"

    def test_golden_cross_is_buy_signal(self, exchange: MockExchange) -> None:
        """金叉突破信号应该判定为买入。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker([])
        )
        info = make_info("ABCUSDT", cross_signal=CrossSignalType.GOLDEN)
        assert strategy._is_buy_signal(info) is True, "金叉应为买入信号"

    def test_dead_cross_not_buy_signal(self, exchange: MockExchange) -> None:
        """死叉信号不应买入。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker([])
        )
        info = make_info("ABCUSDT", cross_signal=CrossSignalType.DEAD)
        assert strategy._is_buy_signal(info) is False, "死叉不应买入"

    def test_near_not_buy_signal(self, exchange: MockExchange) -> None:
        """仅靠近均线（near）不构成买入信号。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker([])
        )
        info = make_info("ABCUSDT", cross_signal=CrossSignalType.NEAR)
        assert strategy._is_buy_signal(info) is False, "near 不应买入"

    def test_no_signal_not_buy(self, exchange: MockExchange) -> None:
        """无任何技术信号时不应买入。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker([])
        )
        info = make_info("ABCUSDT")
        assert strategy._is_buy_signal(info) is False


class TestMicroCapExecuteEntry:
    """测试入场执行逻辑。"""

    @pytest.mark.asyncio
    async def test_opens_position_on_sideways_signal(
        self, exchange: MockExchange
    ) -> None:
        """正常路径：横盘信号 -> 开仓 10 USDT。"""
        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [make_info("ABCUSDT", price=1.0, is_sideways_bottom=True)]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1, "应该开一个仓位"
        assert positions[0].symbol == "ABCUSDT"
        assert positions[0].total_size == 10.0, f"应买入 10 USDT，实际 {positions[0].total_size}"
        assert positions[0].direction == TradeDirection.LONG

    @pytest.mark.asyncio
    async def test_opens_position_on_golden_cross(
        self, exchange: MockExchange
    ) -> None:
        """正常路径：金叉突破信号 -> 开仓。"""
        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [make_info("XYZUSDT", price=2.0, cross_signal=CrossSignalType.GOLDEN)]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(return_value={"XYZUSDT": 2.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1
        assert positions[0].symbol == "XYZUSDT"
        assert positions[0].entry_price == 2.0

    @pytest.mark.asyncio
    async def test_respects_max_positions(self, exchange: MockExchange) -> None:
        """边界：已有 max_positions 个持仓时不再开仓。"""
        # 预先开 2 个仓位
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        exchange.open_position(
            symbol="BBBUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )

        config = MicroCapConfig(max_positions=2, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [make_info("CCCUSDT", price=1.0, is_sideways_bottom=True)]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(return_value={"CCCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "不应该超过 max_positions 限制"
        symbols = {p.symbol for p in positions}
        assert "CCCUSDT" not in symbols, "满了不应再开新仓"

    @pytest.mark.asyncio
    async def test_no_open_without_buy_signal(self, exchange: MockExchange) -> None:
        """信号过滤：候选币无横盘/金叉信号时不开仓。"""
        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [
                make_info("AAAUSDT", cross_signal=CrossSignalType.DEAD),
                make_info("BBBUSDT", cross_signal=CrossSignalType.NEAR),
                make_info("CCCUSDT"),  # 无信号
            ]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(  # type: ignore
            return_value={"AAAUSDT": 1.0, "BBBUSDT": 1.0, "CCCUSDT": 1.0}
        )

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0, "无买入信号不应开仓"

    @pytest.mark.asyncio
    async def test_skip_existing_symbols(self, exchange: MockExchange) -> None:
        """隔离：已有持仓的 symbol 不重复开仓。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )

        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [
                make_info("AAAUSDT", price=1.0, is_sideways_bottom=True),  # 已持仓
                make_info("BBBUSDT", price=2.0, cross_signal=CrossSignalType.GOLDEN),  # 新信号
            ]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(  # type: ignore
            return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0}
        )

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "应只有 2 个仓位（1 旧 + 1 新）"
        symbols = {p.symbol for p in positions}
        assert "BBBUSDT" in symbols, "应该新开 BBBUSDT"
        # AAAUSDT 不应有 ADD 订单
        aaa = [p for p in positions if p.symbol == "AAAUSDT"][0]
        assert len(aaa.orders) == 1, "已持仓 symbol 不应重复开仓"

    @pytest.mark.asyncio
    async def test_open_multiple_within_quota(self, exchange: MockExchange) -> None:
        """混合场景：多个买入信号按配额开仓。"""
        config = MicroCapConfig(max_positions=3, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [
                make_info("AAAUSDT", price=1.0, is_sideways_bottom=True),
                make_info("BBBUSDT", price=2.0, cross_signal=CrossSignalType.GOLDEN),
                make_info("CCCUSDT", price=3.0, is_sideways_bottom=True),
            ]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(  # type: ignore
            return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0, "CCCUSDT": 3.0}
        )

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 3, "应该在配额内开 3 个仓位"
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAAUSDT", "BBBUSDT", "CCCUSDT"}

    @pytest.mark.asyncio
    async def test_empty_candidates_no_error(self, exchange: MockExchange) -> None:
        """空值：候选列表为空时不报错、不开仓。"""
        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker([])
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(return_value={})  # type: ignore

        await strategy.execute()  # 不应抛异常

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_tag_isolation_from_martingale(
        self, exchange: MockExchange
    ) -> None:
        """隔离机制：micro_cap 开仓不影响 martingale 持仓，反之亦然。"""
        # 预先存在一个 martingale 持仓
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="martingale_entry",
        )

        config = MicroCapConfig(max_positions=5, position_size_usdt=10.0)
        picker = FakeMicroCapPicker(
            [make_info("ABCUSDT", price=1.0, is_sideways_bottom=True)]
        )
        strategy = MicroCapStrategy(exchange, config, picker)
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        micro_positions = exchange.get_positions(tag="micro_cap")
        mart_positions = exchange.get_positions(tag="martingale")
        assert len(micro_positions) == 1, "micro_cap 应开 1 仓"
        assert len(mart_positions) == 1, "martingale 持仓应保持不变"
        assert micro_positions[0].symbol == "ABCUSDT"
        assert mart_positions[0].symbol == "BTCUSDT"


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
            FakeMicroCapPicker([]),
        )

        status = strategy.get_status()

        assert status["config"]["max_positions"] == 5
        assert status["open_positions"] == 1
        assert status["total_positions"] == 1

    def test_get_status_empty(self, exchange: MockExchange) -> None:
        """空值：无持仓时状态正确。"""
        strategy = MicroCapStrategy(
            exchange, MicroCapConfig(), FakeMicroCapPicker([])
        )

        status = strategy.get_status()

        assert status["open_positions"] == 0
        assert status["total_positions"] == 0
