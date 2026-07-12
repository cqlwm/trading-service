"""测试 ShortSignalFilter 做空信号过滤器。"""
from __future__ import annotations

import pytest

from trading_service.pickers import ShortSignalFilter, SymbolInfo
from trading_service.types import CrossSignalType


def _make_info(
    symbol: str,
    cross_signal: CrossSignalType | None = None,
    price_vs_sma200: float | None = None,
) -> SymbolInfo:
    """构造测试用 SymbolInfo。"""
    info = SymbolInfo(symbol=symbol)
    info.cross_signal = cross_signal
    info.price_vs_sma200_percent = price_vs_sma200
    return info


class TestShortSignalFilter:
    """测试做空信号过滤逻辑。"""

    @pytest.mark.asyncio
    async def test_keeps_dead_cross(self) -> None:
        """死叉信号应保留。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT", cross_signal=CrossSignalType.DEAD)]
        result = await flt.apply(infos)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_keeps_overbought(self) -> None:
        """价格远高于均线（超买）应保留。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT", price_vs_sma200=20.0)]
        result = await flt.apply(infos)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_drops_golden_cross(self) -> None:
        """金叉信号应丢弃。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT", cross_signal=CrossSignalType.GOLDEN)]
        result = await flt.apply(infos)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_drops_near_signal(self) -> None:
        """靠近均线信号应丢弃。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT", cross_signal=CrossSignalType.NEAR)]
        result = await flt.apply(infos)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_drops_no_signal(self) -> None:
        """无技术信号应丢弃。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT")]
        result = await flt.apply(infos)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_drops_below_threshold(self) -> None:
        """距离均线不够远（低于阈值）应丢弃。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [_make_info("BTCUSDT", price_vs_sma200=10.0)]
        result = await flt.apply(infos)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_mixed_list(self) -> None:
        """混合列表应只保留有做空信号的。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        infos = [
            _make_info("BTCUSDT", cross_signal=CrossSignalType.DEAD),       # 保留
            _make_info("ETHUSDT", cross_signal=CrossSignalType.GOLDEN),    # 丢弃
            _make_info("SOLUSDT", price_vs_sma200=25.0),                    # 保留
            _make_info("ADAUSDT"),                                          # 丢弃
            _make_info("DOTUSDT", price_vs_sma200=5.0),                    # 丢弃
        ]
        result = await flt.apply(infos)
        assert len(result) == 2
        symbols = {r.symbol for r in result}
        assert symbols == {"BTCUSDT", "SOLUSDT"}


def _make_klines_df(
    cross_signal: str | None = None,
    price_vs_sma200: float | None = None,
):
    """构建含指标列的 DataFrame。"""
    import pandas as pd
    return pd.DataFrame([{
        "close": 1.0,
        "cross_signal": cross_signal,
        "price_vs_sma200_percent": price_vs_sma200,
    }])


class TestShortSignalFilterDataFrame:
    """测试从 DataFrame 读取指标。"""

    @pytest.mark.asyncio
    async def test_keeps_dead_cross_from_dataframe(self) -> None:
        """从 DataFrame 读死叉信号应保留。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines = _make_klines_df(cross_signal="dead")
        result = await flt.apply([info])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_keeps_overbought_from_dataframe(self) -> None:
        """从 DataFrame 读超买应保留。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines = _make_klines_df(price_vs_sma200=20.0)
        result = await flt.apply([info])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_drops_golden_from_dataframe(self) -> None:
        """从 DataFrame 读金叉应丢弃。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines = _make_klines_df(cross_signal="golden")
        result = await flt.apply([info])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_dataframe_takes_priority(self) -> None:
        """DataFrame 有值时优先于旧字段。"""
        flt = ShortSignalFilter(overbought_threshold=15.0)
        info = SymbolInfo(symbol="BTCUSDT", cross_signal=CrossSignalType.GOLDEN)  # 旧字段金叉
        info.klines = _make_klines_df(cross_signal="dead")  # DataFrame 死叉
        result = await flt.apply([info])
        assert len(result) == 1, "应以 DataFrame 为准（死叉保留）"
