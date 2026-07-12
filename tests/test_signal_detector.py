"""信号检测器测试。

验证检测器作为策略组件的信号检测、落盘功能。
检测器接收候选币列表（SymbolInfo），产出信号。
指标从 klines DataFrame 最后一行读取。
"""
from __future__ import annotations

import pytest

import pandas as pd

from trading_service.detectors.technical import TechnicalSignalDetector
from trading_service.exchange import MockExchange
from trading_service.pickers import SymbolInfo
from trading_service.types import CrossSignalType


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    return MockExchange(InMemoryTradingRepository())


def make_klines_df(
    cross_signal: str | None = None,
    price_vs_sma200: float | None = None,
    sma_200: float | None = None,
    is_sideways: bool = False,
    volatility: float | None = None,
) -> pd.DataFrame:
    """构建一个含指标列的 DataFrame（模拟 TechnicalAnalysisFilter 的输出）。"""
    return pd.DataFrame([{
        "datetime": 0,
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
        "sma_200": sma_200,
        "cross_signal": cross_signal,
        "price_vs_sma200_percent": price_vs_sma200,
        "volatility_10": volatility,
        "is_sideways_bottom": is_sideways,
    }])


def make_info(
    symbol: str,
    cross_signal: CrossSignalType | None = None,
    is_sideways_bottom: bool = False,
    sma_200: float | None = None,
    price_vs_sma200_percent: float | None = None,
    volatility_10: float | None = None,
) -> SymbolInfo:
    """构造一个带 klines["4h"] DataFrame 的 SymbolInfo。"""
    cross_str = cross_signal.value if cross_signal else None
    info = SymbolInfo(symbol=symbol)
    info.klines["4h"] = make_klines_df(
        cross_signal=cross_str,
        price_vs_sma200=price_vs_sma200_percent,
        sma_200=sma_200,
        is_sideways=is_sideways_bottom,
        volatility=volatility_10,
    )
    return info


class TestTechnicalSignalDetector:
    """测试技术分析信号检测器。"""

    @pytest.mark.asyncio
    async def test_detect_golden_cross(self, exchange: MockExchange) -> None:
        """金叉信号应被正确检测。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        candidates = [make_info("BTCUSDT", cross_signal=CrossSignalType.GOLDEN, sma_200=50000, price_vs_sma200_percent=2.5)]

        results = await detector.detect(candidates)

        assert len(results) == 1
        assert results[0].symbol == "BTCUSDT"
        assert results[0].signal_type == "golden_cross"
        assert results[0].direction == "bullish"
        assert results[0].severity == 3

    @pytest.mark.asyncio
    async def test_detect_dead_cross(self, exchange: MockExchange) -> None:
        """死叉信号应被正确检测。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        candidates = [make_info("ETHUSDT", cross_signal=CrossSignalType.DEAD, sma_200=3000, price_vs_sma200_percent=-3.0)]

        results = await detector.detect(candidates)

        assert len(results) == 1
        assert results[0].signal_type == "dead_cross"
        assert results[0].direction == "bearish"

    @pytest.mark.asyncio
    async def test_detect_sideways_bottom(self, exchange: MockExchange) -> None:
        """横盘底部信号应被正确检测。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        candidates = [make_info("SOLUSDT", is_sideways_bottom=True, volatility_10=0.05)]

        results = await detector.detect(candidates)

        assert len(results) == 1
        assert results[0].signal_type == "sideways_bottom"
        assert results[0].direction == "neutral"
        assert results[0].severity == 2

    @pytest.mark.asyncio
    async def test_detect_no_signal(self, exchange: MockExchange) -> None:
        """无技术信号的候选币不产出信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        candidates = [make_info("BTCUSDT", cross_signal=None)]

        results = await detector.detect(candidates)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_detect_multiple_candidates(self, exchange: MockExchange) -> None:
        """多个候选币应分别检测。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        candidates = [
            make_info("BTCUSDT", cross_signal=CrossSignalType.GOLDEN),
            make_info("ETHUSDT", cross_signal=CrossSignalType.DEAD),
            make_info("SOLUSDT", cross_signal=None),
        ]

        results = await detector.detect(candidates)

        assert len(results) == 2
        types = {r.signal_type for r in results}
        assert types == {"golden_cross", "dead_cross"}

    @pytest.mark.asyncio
    async def test_detect_empty_candidates(self, exchange: MockExchange) -> None:
        """空候选列表返回空信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        results = await detector.detect([])
        assert len(results) == 0


class TestDetectorAsStrategyComponent:
    """测试检测器作为策略组件被 run_detectors 调用。"""

    @pytest.mark.asyncio
    async def test_run_detectors_persists_signals(self, exchange: MockExchange) -> None:
        """策略 run_detectors 应将检测器产出的信号落盘。"""
        from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
        from trading_service.pickers import ISymbolPicker

        class FakePicker(ISymbolPicker):
            async def pick(self) -> list[SymbolInfo]:
                return []

        class TestStrategy(Strategy):
            name = "test"
            cron = ""

            async def execute(self, execution_id: str = "") -> list[StrategyAction]:
                return []

            def get_status(self) -> dict:
                return {}

        detector = TechnicalSignalDetector(repo=exchange.db)
        strategy = TestStrategy(
            exchange, StrategyConfig(), FakePicker(),
            signal_detectors=[detector],
        )

        candidates = [make_info("BTCUSDT", cross_signal=CrossSignalType.GOLDEN, sma_200=50000)]
        saved = await strategy.run_detectors(candidates)

        assert len(saved) == 1
        assert saved[0].symbol == "BTCUSDT"
        assert saved[0].signal_type == "golden_cross"
        # 验证信号已落盘
        db_signals = exchange.db.list_signals(signal_type="golden_cross")
        assert len(db_signals) == 1

    @pytest.mark.asyncio
    async def test_run_detectors_no_detectors(self, exchange: MockExchange) -> None:
        """无检测器时 run_detectors 返回空列表。"""
        from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
        from trading_service.pickers import ISymbolPicker

        class FakePicker(ISymbolPicker):
            async def pick(self) -> list[SymbolInfo]:
                return []

        class TestStrategy(Strategy):
            name = "test"
            cron = ""

            async def execute(self, execution_id: str = "") -> list[StrategyAction]:
                return []

            def get_status(self) -> dict:
                return {}

        strategy = TestStrategy(exchange, StrategyConfig(), FakePicker())
        saved = await strategy.run_detectors([make_info("BTCUSDT")])
        assert len(saved) == 0


class TestDetectorDataFrameRead:
    """测试检测器从 DataFrame 读取指标。"""

    @pytest.mark.asyncio
    async def test_read_golden_cross_from_dataframe(self, exchange: MockExchange) -> None:
        """从 DataFrame 读取金叉信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines["4h"] = make_klines_df(cross_signal="golden", sma_200=50000, price_vs_sma200=2.5)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "golden_cross"
        assert results[0].metadata["sma_200"] == 50000

    @pytest.mark.asyncio
    async def test_read_dead_cross_from_dataframe(self, exchange: MockExchange) -> None:
        """从 DataFrame 读取死叉信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        info = SymbolInfo(symbol="ETHUSDT")
        info.klines["4h"] = make_klines_df(cross_signal="dead", sma_200=3000, price_vs_sma200=-3.0)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "dead_cross"

    @pytest.mark.asyncio
    async def test_read_sideways_from_dataframe(self, exchange: MockExchange) -> None:
        """从 DataFrame 读取横盘信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        info = SymbolInfo(symbol="SOLUSDT")
        info.klines["4h"] = make_klines_df(is_sideways=True, volatility=5.0)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "sideways_bottom"

    @pytest.mark.asyncio
    async def test_no_klines_returns_empty(self, exchange: MockExchange) -> None:
        """无 klines 数据的候选币不产出信号。"""
        detector = TechnicalSignalDetector(repo=exchange.db)
        info = SymbolInfo(symbol="BTCUSDT")  # klines={}

        results = await detector.detect([info])

        assert len(results) == 0
