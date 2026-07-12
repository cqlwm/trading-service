"""测试 MicroCapStrategy 选币 + 信号检测 + 信号驱动入场。

策略流程（重构后）：
1. 选币：symbol_picker.pick() 获取候选币（已含技术分析字段）
2. 信号检测：检测器接收候选币，产出 golden_cross 信号落盘
3. 决策：从 DB 拉取金叉信号，排除已持仓 symbol 后开仓
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
from trading_service.types import CrossSignalType, TradeDirection


class FakeMicroCapPicker(ISymbolPicker):
    """内存版选币器 - 返回带技术分析字段的 SymbolInfo。"""

    def __init__(self, symbols: list[SymbolInfo]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        return list(self.symbols)


def make_info(
    symbol: str,
    cross_signal: CrossSignalType | None = None,
    is_sideways_bottom: bool = False,
    sma_200: float | None = None,
    price_vs_sma200_percent: float | None = None,
) -> SymbolInfo:
    return SymbolInfo(
        symbol=symbol,
        cross_signal=cross_signal,
        is_sideways_bottom=is_sideways_bottom,
        sma_200=sma_200,
        price_vs_sma200_percent=price_vs_sma200_percent,
    )


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    return MockExchange(InMemoryTradingRepository())


def make_strategy(
    exchange: MockExchange,
    picker_symbols: list[SymbolInfo] | None = None,
    max_positions: int = 5,
) -> MicroCapStrategy:
    """创建带技术信号检测器的微市值策略。"""
    from trading_service.detectors.technical import TechnicalSignalDetector

    config = MicroCapConfig(max_positions=max_positions, position_size_usdt=10.0)
    picker = FakeMicroCapPicker(picker_symbols or [])
    detector = TechnicalSignalDetector(repo=exchange.db)
    return MicroCapStrategy(
        exchange, config, picker,
        signal_detectors=[detector],
    )


class TestMicroCapSignalDriven:
    """测试选币 + 信号检测 + 信号驱动入场。"""

    @pytest.mark.asyncio
    async def test_golden_cross_signal_triggers_open(self, exchange: MockExchange) -> None:
        """正常路径：选币 -> 金叉信号落盘 -> 从 DB 拉取信号开仓。"""
        strategy = make_strategy(exchange, [
            make_info("ABCUSDT", cross_signal=CrossSignalType.GOLDEN, sma_200=1.0, price_vs_sma200_percent=2.0),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1, "应该开一个仓位"
        assert positions[0].symbol == "ABCUSDT"
        assert positions[0].total_size == 10.0
        assert positions[0].direction == TradeDirection.LONG

    @pytest.mark.asyncio
    async def test_no_golden_cross_no_open(self, exchange: MockExchange) -> None:
        """候选币无金叉信号时不开仓。"""
        strategy = make_strategy(exchange, [
            make_info("AAAUSDT", cross_signal=CrossSignalType.DEAD),
            make_info("BBBUSDT", cross_signal=CrossSignalType.NEAR),
            make_info("CCCUSDT"),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"AAAUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0, "无金叉信号不应开仓"

    @pytest.mark.asyncio
    async def test_empty_candidates_no_error(self, exchange: MockExchange) -> None:
        """空候选列表不报错、不开仓。"""
        strategy = make_strategy(exchange, [])
        exchange.fetch_prices = AsyncMock(return_value={})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_respects_max_positions(self, exchange: MockExchange) -> None:
        """边界：已有 max_positions 个持仓时不再开仓。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        exchange.open_position(
            symbol="BBBUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        strategy = make_strategy(exchange, [
            make_info("CCCUSDT", cross_signal=CrossSignalType.GOLDEN),
        ], max_positions=2)
        exchange.fetch_prices = AsyncMock(return_value={"CCCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "不应该超过 max_positions"
        assert "CCCUSDT" not in {p.symbol for p in positions}

    @pytest.mark.asyncio
    async def test_skip_existing_symbols(self, exchange: MockExchange) -> None:
        """已有持仓的 symbol 不重复开仓。"""
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="existing",
        )
        strategy = make_strategy(exchange, [
            make_info("AAAUSDT", cross_signal=CrossSignalType.GOLDEN),
            make_info("BBBUSDT", cross_signal=CrossSignalType.GOLDEN),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 2, "应有 2 个仓位（1 旧 + 1 新）"
        assert "BBBUSDT" in {p.symbol for p in positions}

    @pytest.mark.asyncio
    async def test_action_record_links_signal_ids(self, exchange: MockExchange) -> None:
        """动作记录的 signal_ids 应关联到落盘的信号。"""
        strategy = make_strategy(exchange, [
            make_info("ABCUSDT", cross_signal=CrossSignalType.GOLDEN, sma_200=1.0, price_vs_sma200_percent=2.0),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 1
        actions = exchange.db.list_actions_by_position(positions[0].id)
        assert len(actions) == 1
        assert len(actions[0].signal_ids) == 1, "应关联 1 个信号 ID"

    @pytest.mark.asyncio
    async def test_multiple_golden_cross_within_quota(self, exchange: MockExchange) -> None:
        """多个金叉信号按配额开仓。"""
        strategy = make_strategy(exchange, [
            make_info("AAAUSDT", cross_signal=CrossSignalType.GOLDEN),
            make_info("BBBUSDT", cross_signal=CrossSignalType.GOLDEN),
            make_info("CCCUSDT", cross_signal=CrossSignalType.GOLDEN),
        ], max_positions=3)
        exchange.fetch_prices = AsyncMock(  # type: ignore
            return_value={"AAAUSDT": 1.0, "BBBUSDT": 2.0, "CCCUSDT": 3.0}
        )

        await strategy.execute()

        positions = exchange.get_positions(tag="micro_cap")
        assert len(positions) == 3
        assert {p.symbol for p in positions} == {"AAAUSDT", "BBBUSDT", "CCCUSDT"}

    @pytest.mark.asyncio
    async def test_tag_isolation_from_martingale(self, exchange: MockExchange) -> None:
        """micro_cap 开仓不影响 martingale 持仓。"""
        exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="entry",
        )
        strategy = make_strategy(exchange, [
            make_info("ABCUSDT", cross_signal=CrossSignalType.GOLDEN),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        assert len(exchange.get_positions(tag="micro_cap")) == 1
        assert len(exchange.get_positions(tag="martingale")) == 1

    @pytest.mark.asyncio
    async def test_signal_persisted_to_db(self, exchange: MockExchange) -> None:
        """检测器产出的信号应落盘到 trading_signals。"""
        strategy = make_strategy(exchange, [
            make_info("ABCUSDT", cross_signal=CrossSignalType.GOLDEN, sma_200=1.0, price_vs_sma200_percent=2.0),
            make_info("XYZUSDT", cross_signal=CrossSignalType.DEAD, sma_200=2.0, price_vs_sma200_percent=-2.0),
        ])
        exchange.fetch_prices = AsyncMock(return_value={"ABCUSDT": 1.0})  # type: ignore

        await strategy.execute()

        # 应有 1 条金叉 + 1 条死叉信号落盘
        golden = exchange.db.list_signals(signal_type="golden_cross")
        dead = exchange.db.list_signals(signal_type="dead_cross")
        assert len(golden) == 1
        assert len(dead) == 1


class TestMicroCapStatus:
    """测试状态报告。"""

    def test_get_status_returns_config_and_counts(self, exchange: MockExchange) -> None:
        exchange.open_position(
            symbol="AAAUSDT", direction=TradeDirection.LONG,
            size=10, price=1.0, tag="micro_cap", reason_text="entry",
        )
        strategy = make_strategy(exchange, [], max_positions=5)

        status = strategy.get_status()

        assert status["config"]["max_positions"] == 5
        assert status["open_positions"] == 1
        assert status["total_positions"] == 1

    def test_get_status_empty(self, exchange: MockExchange) -> None:
        strategy = make_strategy(exchange, [])

        status = strategy.get_status()

        assert status["open_positions"] == 0
        assert status["total_positions"] == 0
