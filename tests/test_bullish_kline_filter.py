"""测试 BullishKlineFilter 阳线过滤器。

拉取指定 interval 的 K 线，存入 info.klines[interval]，丢弃昨日非阳线代币。
阳线定义：昨日（倒数第二根）收盘价 >= 开盘价。
"""
from __future__ import annotations

import pytest

from trading_service.clients import BinanceFutureKline
from trading_service.pickers import BullishKlineFilter, SymbolInfo
from trading_service.pickers.pipeline import ISymbolFilter


def make_kline(open_p: float, close_p: float) -> BinanceFutureKline:
    """构造一根 K 线（阳线: close>=open）。"""
    high = max(open_p, close_p)
    low = min(open_p, close_p)
    return BinanceFutureKline(
        open_time=0, open_price=str(open_p), high_price=str(high),
        low_price=str(low), close_price=str(close_p), volume="100",
        close_time=0, quote_volume="0", trade_count=0,
        taker_buy_base_volume="0", taker_buy_quote_volume="0", ignore="0",
    )


# [yesterday, today]；[-2] 即 yesterday
BULLISH_KLINES = [make_kline(10, 12), make_kline(12, 11)]   # [-2] 阳线(close12>=open10)
BEARISH_KLINES = [make_kline(12, 10), make_kline(10, 11)]   # [-2] 阴线(close10<open12)


class FakeKlineClient:
    """最小化 client：只实现 BullishKlineFilter 用到的 get_future_klines。"""

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


class TestBullishKlineFilterInterface:
    """接口契约测试。"""

    def test_implements_isymbol_filter(self) -> None:
        """✅ BullishKlineFilter 必须实现 ISymbolFilter。"""
        f = BullishKlineFilter(client=FakeKlineClient({}))
        assert isinstance(f, ISymbolFilter)


class TestBullishKlineFilterLogic:
    """阳线过滤逻辑测试。"""

    @pytest.mark.asyncio
    async def test_keeps_bullish(self) -> None:
        """正常路径：昨日阳线 -> 保留。"""
        client = FakeKlineClient({"ABCUSDT": BULLISH_KLINES})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        result = await flt.apply([make_info("ABCUSDT")])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_drops_bearish(self) -> None:
        """边界：昨日阴线 -> 丢弃。"""
        client = FakeKlineClient({"BEARUSDT": BEARISH_KLINES})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        result = await flt.apply([make_info("BEARUSDT")])
        assert len(result) == 0, "昨日阴线应被丢弃"

    @pytest.mark.asyncio
    async def test_mixed_list(self) -> None:
        """组合：阳线保留、阴线丢弃。"""
        client = FakeKlineClient({
            "BULLUSDT": BULLISH_KLINES,
            "BEARUSDT": BEARISH_KLINES,
        })
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        result = await flt.apply([make_info("BULLUSDT"), make_info("BEARUSDT")])
        assert len(result) == 1
        assert result[0].symbol == "BULLUSDT"


class TestBullishKlineFilterCaching:
    """K 线缓存测试。"""

    @pytest.mark.asyncio
    async def test_stores_klines_in_dict(self) -> None:
        """正常路径：拉取的 K 线存入 info.klines[interval]。"""
        client = FakeKlineClient({"ABCUSDT": BULLISH_KLINES})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        info = make_info("ABCUSDT")

        await flt.apply([info])

        assert "1d" in info.klines, "应存入 klines['1d']"
        assert len(info.klines["1d"]) == 2

    @pytest.mark.asyncio
    async def test_does_not_refetch_cached(self) -> None:
        """幂等性：已有缓存的 interval 不重新拉取。"""
        client = FakeKlineClient({"ABCUSDT": BULLISH_KLINES})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        info = make_info("ABCUSDT")

        await flt.apply([info])
        call_count_after_first = len(client.calls)

        await flt.apply([info])
        assert len(client.calls) == call_count_after_first, "缓存命中不应重新拉取"


class TestBullishKlineFilterBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_empty_infos_returns_empty(self) -> None:
        """空值：输入空列表 -> 返回空列表。"""
        flt = BullishKlineFilter(client=FakeKlineClient({}))
        result = await flt.apply([])
        assert result == []

    @pytest.mark.asyncio
    async def test_insufficient_klines_drops(self) -> None:
        """边界：K 线不足 2 根 -> 丢弃（无法取昨日）。"""
        client = FakeKlineClient({"ABCUSDT": [make_kline(10, 12)]})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        result = await flt.apply([make_info("ABCUSDT")])
        assert len(result) == 0, "K线不足应丢弃"

    @pytest.mark.asyncio
    async def test_no_klines_for_symbol_drops(self) -> None:
        """边界：client 返回空 K 线 -> 丢弃。"""
        client = FakeKlineClient({"ABCUSDT": []})
        flt = BullishKlineFilter(client=client, interval="1d", limit=5)
        result = await flt.apply([make_info("ABCUSDT")])
        assert len(result) == 0
