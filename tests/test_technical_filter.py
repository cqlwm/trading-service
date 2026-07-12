"""测试 TechnicalAnalysisFilter（TDD 红阶段）。

技术分析独立阶段：逐个拉K线 + 调 analyzer.detect_200sma_signal + 写入 klines DataFrame。
关键不变量：纯增强--analyzer 返回 None 时 SymbolInfo 数量不减、DataFrame 不含信号列。

测试覆盖：正常路径增强、纯增强不丢弃、边界（空/数据不足）、幂等。
使用 FakeBinanceClient + 真 TechnicalAnalyzer，零网络。
"""
from __future__ import annotations

import inspect
from typing import Protocol

import pytest

from trading_service.clients import BinanceFutureKline
from trading_service.pickers import SymbolInfo, TechnicalAnalyzer
from trading_service.pickers.pipeline import ISymbolFilter
from trading_service.pickers.technical_filter import TechnicalAnalysisFilter
from trading_service.types import CrossSignalType


def make_kline(
    open_price: float, high: float, low: float, close: float,
) -> BinanceFutureKline:
    """构造一根内存 K 线。"""
    return BinanceFutureKline(
        open_time=0, open_price=str(open_price), high_price=str(high),
        low_price=str(low), close_price=str(close), volume="100",
        close_time=0, quote_volume="0", trade_count=0,
        taker_buy_base_volume="0", taker_buy_quote_volume="0", ignore="0",
    )


def make_flat_klines(count: int, price: float = 100.0) -> list[BinanceFutureKline]:
    """构造 count 根价格恒定的 K 线。"""
    return [make_kline(price, price, price, price) for _ in range(count)]


class _GetKlinesFn(Protocol):
    def __call__(self, symbol: str, interval: str, limit: int = ...) -> list[BinanceFutureKline]: ...


class FakeKlineClient:
    """最小化 client：只实现 TechnicalAnalysisFilter 用到的 get_future_klines。

    按 symbol 映射到预置的 K 线列表，支持不同 symbol 返回不同数据。
    """

    def __init__(self, klines_by_symbol: dict[str, list[BinanceFutureKline]]) -> None:
        self._klines = klines_by_symbol
        self.calls: list[tuple[str, str, int]] = []

    def get_future_klines(
        self, symbol: str, interval: str, limit: int = 500,
    ) -> list[BinanceFutureKline]:
        self.calls.append((symbol, interval, limit))
        return self._klines.get(symbol, [])


def make_info(symbol: str) -> SymbolInfo:
    return SymbolInfo(symbol=symbol)


def _latest_signal_col(info: SymbolInfo, col: str) -> object:
    """从 klines["4h"] 最后一行读取信号列值。列不存在时返回 None。"""
    df = info.klines.get("4h")
    if df is None or len(df) == 0:
        return None
    if col not in df.columns:
        return None
    return df.iloc[-1][col]


class TestTechnicalFilterInterface:
    """接口契约测试。"""

    def test_implements_isymbol_filter(self) -> None:
        """✅ TechnicalAnalysisFilter 必须实现 ISymbolFilter。"""
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(),
            client=FakeKlineClient({}),
        )
        assert isinstance(f, ISymbolFilter)

    def test_apply_is_async(self) -> None:
        """✅ apply() 必须是 async。"""
        assert inspect.iscoroutinefunction(TechnicalAnalysisFilter.apply), \
            "❌ TechnicalAnalysisFilter.apply() 必须是 async"


class TestTechnicalFilterEnrichment:
    """正常路径：增强技术字段。"""

    @pytest.mark.asyncio
    async def test_enriches_golden_cross_fields(self) -> None:
        """正常路径：金叉 K 线 -> 回填 cross_signal=golden 及相关字段。"""
        # 200 根低价(50) + 1 根过渡 + 1 根上穿(70) -> 金叉
        klines = make_flat_klines(200, 50.0)
        klines.append(make_kline(50, 50, 50, 50))
        klines.append(make_kline(48, 70, 48, 70))

        client = FakeKlineClient({"ABCUSDT": klines})
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=client, kline_interval="4h",
        )

        result = await f.apply([make_info("ABCUSDT")])

        assert len(result) == 1
        info = result[0]
        assert "4h" in info.klines, "klines['4h'] 应已构建"
        assert _latest_signal_col(info, "cross_signal") == CrossSignalType.GOLDEN.value, \
            f"应写入 golden，实际 {_latest_signal_col(info, 'cross_signal')}"
        assert _latest_signal_col(info, "sma_200") is not None, "sma_200 列应有值"
        assert _latest_signal_col(info, "price_vs_sma200_percent") is not None
        assert _latest_signal_col(info, "volatility_10") is not None

    @pytest.mark.asyncio
    async def test_fetches_correct_kline_interval_and_limit(self) -> None:
        """正常路径：按配置的 kline_interval 拉 210 根 K 线。"""
        client = FakeKlineClient({"ABCUSDT": make_flat_klines(210, 100.0)})
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=client, kline_interval="1d",
        )
        await f.apply([make_info("ABCUSDT")])
        assert client.calls == [("ABCUSDT", "1d", 210)], \
            f"应按 interval=1d, limit=210 拉K线，实际 {client.calls}"


class TestTechnicalFilterPureEnrichment:
    """纯增强不变量：analyzer 返回 None 时不丢弃、字段保持默认。"""

    @pytest.mark.asyncio
    async def test_no_drop_when_signal_none(self) -> None:
        """纯增强：远离均线且无穿越（返回 None）-> 数量不减。"""
        # 价格稳定在 120（远高于均线 100），无穿越 -> analyzer 返回 None
        klines = make_flat_klines(200, 100.0)
        klines.extend(make_flat_klines(15, 120.0))

        client = FakeKlineClient({"AAAUSDT": klines, "BBBUSDT": klines})
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=client,
        )

        infos = [make_info("AAAUSDT"), make_info("BBBUSDT")]
        result = await f.apply(infos)

        assert len(result) == 2, "纯增强不应丢弃任何 SymbolInfo"

    @pytest.mark.asyncio
    async def test_fields_keep_default_when_signal_none(self) -> None:
        """纯增强：信号为 None 时 DataFrame 不含信号列。"""
        klines = make_flat_klines(200, 100.0)
        klines.extend(make_flat_klines(15, 120.0))  # 远离均线 -> None

        client = FakeKlineClient({"ABCUSDT": klines})
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=client,
        )

        result = await f.apply([make_info("ABCUSDT")])
        info = result[0]
        assert "4h" in info.klines
        df_4h = info.klines["4h"]
        assert "cross_signal" not in df_4h.columns, "无信号时不应写入 cross_signal 列"
        assert "is_sideways_bottom" not in df_4h.columns
        assert "volatility_10" not in df_4h.columns

    @pytest.mark.asyncio
    async def test_mixed_signals_all_kept(self) -> None:
        """组合：有信号的增强、无信号的保留，全部不丢弃。"""
        golden_klines = make_flat_klines(200, 50.0)
        golden_klines.append(make_kline(50, 50, 50, 50))
        golden_klines.append(make_kline(48, 70, 48, 70))  # 金叉

        far_klines = make_flat_klines(200, 100.0)
        far_klines.extend(make_flat_klines(15, 120.0))  # 远离 -> None

        client = FakeKlineClient({
            "GOLDUSDT": golden_klines,
            "FARUSDT": far_klines,
        })
        f = TechnicalAnalysisFilter(analyzer=TechnicalAnalyzer(), client=client)

        result = await f.apply([make_info("GOLDUSDT"), make_info("FARUSDT")])
        assert len(result) == 2, "两个都应保留"
        by_sym = {i.symbol: i for i in result}
        assert _latest_signal_col(by_sym["GOLDUSDT"], "cross_signal") == CrossSignalType.GOLDEN.value
        assert _latest_signal_col(by_sym["FARUSDT"], "cross_signal") is None


class TestTechnicalFilterBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_empty_infos_returns_empty(self) -> None:
        """空值：输入空列表 -> 返回空列表，不报错。"""
        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=FakeKlineClient({}),
        )
        result = await f.apply([])
        assert result == []

    @pytest.mark.asyncio
    async def test_insufficient_klines_keeps_defaults(self) -> None:
        """边界：K 线不足 201 根 -> analyzer 返回 None -> 不构建 klines["4h"]。"""
        client = FakeKlineClient({"ABCUSDT": make_flat_klines(200, 100.0)})
        f = TechnicalAnalysisFilter(analyzer=TechnicalAnalyzer(), client=client)

        result = await f.apply([make_info("ABCUSDT")])
        assert len(result) == 1
        assert "4h" not in result[0].klines, "K线不足不应构建 klines['4h']"

    @pytest.mark.asyncio
    async def test_no_klines_for_symbol_keeps_defaults(self) -> None:
        """边界：client 返回空 K 线 -> 不构建 klines["4h"]，不报错。"""
        client = FakeKlineClient({"ABCUSDT": []})
        f = TechnicalAnalysisFilter(analyzer=TechnicalAnalyzer(), client=client)

        result = await f.apply([make_info("ABCUSDT")])
        assert len(result) == 1
        assert "4h" not in result[0].klines


class TestTechnicalFilterIdempotency:
    """幂等性测试。"""

    @pytest.mark.asyncio
    async def test_two_applies_consistent(self) -> None:
        """幂等性：同一输入两次 apply，DataFrame 信号列一致（用新输入对象）。"""
        golden_klines = make_flat_klines(200, 50.0)
        golden_klines.append(make_kline(50, 50, 50, 50))
        golden_klines.append(make_kline(48, 70, 48, 70))

        client = FakeKlineClient({"ABCUSDT": golden_klines})
        f = TechnicalAnalysisFilter(analyzer=TechnicalAnalyzer(), client=client)

        r1 = await f.apply([make_info("ABCUSDT")])
        r2 = await f.apply([make_info("ABCUSDT")])
        assert _latest_signal_col(r1[0], "cross_signal") == CrossSignalType.GOLDEN.value
        assert _latest_signal_col(r2[0], "cross_signal") == CrossSignalType.GOLDEN.value
        assert _latest_signal_col(r1[0], "sma_200") == _latest_signal_col(r2[0], "sma_200")
