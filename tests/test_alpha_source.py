"""测试 AlphaTokenSource（TDD 红阶段）。

AlphaTokenSource 是从 SimpleAlphaSymbolPicker 瘦身而来的数据源：
只做基础筛选（市值<5000万 + 合约可交易 + 昨日阳线），不做技术分析。

关键断言：
1. 输出的 SymbolInfo 技术字段全为默认值（None/False）——证明技术分析已剥离
2. 基础筛选逻辑正确：市值超限/不可交易/昨日阴线 -> 被过滤
3. 实现 ISymbolSource

使用 FakeClient + 构造内存数据，零网络。
"""
from __future__ import annotations

import inspect

import pytest

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceFutureExchangeInfo,
    BinanceFutureKline,
    BinanceFutureSymbol,
)
from trading_service.pickers.pipeline import ISymbolSource
from trading_service.pickers.symbol_picker import AlphaTokenSource


def make_alpha_token(symbol: str, market_cap: float | None) -> BinanceAlphaToken:
    """构造一个 Alpha 代币（用 API alias 字段名，仅填充 source 用到 + 必填字段）。"""
    return BinanceAlphaToken.model_validate({
        "tokenId": f"id-{symbol}",
        "chainId": 1,
        "contractAddress": f"0x{symbol}",
        "name": symbol,
        "symbol": symbol,
        "price": "1.0",
        "alphaId": f"alpha-{symbol}",
        "marketCap": market_cap,
    })


def make_symbol_info_row(
    base: str,
    status: str = "TRADING",
    delivery_date: int = 4133404800000,
) -> BinanceFutureSymbol:
    """构造一个可交易的合约交易对（仅填充 source 用到的字段）。

    delivery_date 默认为永续合约哨兵值（永不到期）；即将下架的代币传入具体时点。
    """
    return BinanceFutureSymbol(
        symbol=f"{base}USDT", pair=f"{base}USDT", contractType="PERPETUAL",
        deliveryDate=delivery_date, onboardDate=0, status=status, maintMarginPercent="0",
        requiredMarginPercent="0", baseAsset=base, quoteAsset="USDT",
        marginAsset="USDT", pricePrecision=8, quantityPrecision=8,
        baseAssetPrecision=8, quotePrecision=8, underlyingType="COIN",
        underlyingSubType=[], triggerProtect="0", liquidationFee="0",
        marketTakeBound="0", filters=[], orderTypes=[], timeInForce=[],
    )


def make_kline(open_p: float, close_p: float) -> BinanceFutureKline:
    """构造一根日 K 线（阳线: close>=open）。"""
    high = max(open_p, close_p)
    low = min(open_p, close_p)
    return BinanceFutureKline(
        open_time=0, open_price=str(open_p), high_price=str(high),
        low_price=str(low), close_price=str(close_p), volume="100",
        close_time=0, quote_volume="0", trade_count=0,
        taker_buy_base_volume="0", taker_buy_quote_volume="0", ignore="0",
    )


class FakeAlphaClient:
    """最小化 client：实现 AlphaTokenSource 用到的三个方法。"""

    def __init__(
        self,
        alpha_tokens: list[BinanceAlphaToken],
        symbols: list[BinanceFutureSymbol],
        klines_by_symbol: dict[str, list[BinanceFutureKline]] | None = None,
    ) -> None:
        self._alpha_tokens = alpha_tokens
        self._symbols = symbols
        self._klines = klines_by_symbol or {}

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        return self._alpha_tokens

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        return BinanceFutureExchangeInfo(
            exchangeFilters=[], rateLimits=[], serverTime=0,
            assets=[], symbols=self._symbols, timezone="UTC",
        )

    def get_future_klines(
        self, symbol: str, interval: str, limit: int = 500,
    ) -> list[BinanceFutureKline]:
        return self._klines.get(symbol, [])


# 用于检查阳线：source 取 klines_1d[-2] 作为"昨日K线"。
# 列表为 [yesterday, today]；[-2] 即 yesterday，需为阳线(close>=open)。
BULLISH_KLINES = [make_kline(10, 12), make_kline(12, 11)]   # [-2] 阳线(close12>=open10)
BEARISH_KLINES = [make_kline(12, 10), make_kline(10, 11)]   # [-2] 阴线(close10<open12)


def _klines_for(status: str) -> list[BinanceFutureKline]:
    return BULLISH_KLINES if status == "bull" else BEARISH_KLINES


class TestAlphaSourceInterface:
    """接口契约测试。"""

    def test_implements_isymbol_source(self) -> None:
        """✅ AlphaTokenSource 必须实现 ISymbolSource。"""
        source = AlphaTokenSource(client=FakeAlphaClient([], []))
        assert isinstance(source, ISymbolSource)

    def test_fetch_is_async(self) -> None:
        """✅ fetch() 必须是 async。"""
        assert inspect.iscoroutinefunction(AlphaTokenSource.fetch), \
            "❌ AlphaTokenSource.fetch() 必须是 async"

    def test_constructor_has_no_analyzer(self) -> None:
        """✅ AlphaTokenSource 构造函数不再接受 analyzer 参数（技术分析已剥离）。"""
        import inspect as _inspect
        sig = _inspect.signature(AlphaTokenSource.__init__)
        assert "analyzer" not in sig.parameters, \
            "❌ AlphaTokenSource 不应再有 analyzer 参数"
        assert "enable_technical_filter" not in sig.parameters, \
            "❌ AlphaTokenSource 不应再有 enable_technical_filter 参数"


class TestAlphaSourceFiltering:
    """基础筛选逻辑测试。"""

    @pytest.mark.asyncio
    async def test_filters_below_cap_tradable_bullish(self) -> None:
        """正常路径：市值<5000万 + 可交易 + 昨日阳线 -> 保留。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],
            symbols=[make_symbol_info_row("ABC")],
            klines_by_symbol={"ABCUSDT": BULLISH_KLINES},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].symbol == "ABCUSDT"
        assert result[0].market_cap == 10_000_000

    @pytest.mark.asyncio
    async def test_drops_above_market_cap(self) -> None:
        """边界：市值 >= 5000万 -> 过滤掉。"""
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("SMALL", 10_000_000),
                make_alpha_token("BIG", 60_000_000),  # 超 5000 万
            ],
            symbols=[make_symbol_info_row("SMALL"), make_symbol_info_row("BIG")],
            klines_by_symbol={
                "SMALLUSDT": BULLISH_KLINES, "BIGUSDT": BULLISH_KLINES,
            },
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert [i.symbol for i in result] == ["SMALLUSDT"]

    @pytest.mark.asyncio
    async def test_drops_not_tradable(self) -> None:
        """边界：无对应可交易合约 -> 过滤掉。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("NOCONTRACT", 10_000_000)],
            symbols=[],  # 没有可交易合约
            klines_by_symbol={},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert result == []

    @pytest.mark.asyncio
    async def test_drops_bearish_yesterday(self) -> None:
        """边界：昨日阴线 -> 过滤掉。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("BEAR", 10_000_000)],
            symbols=[make_symbol_info_row("BEAR")],
            klines_by_symbol={"BEARUSDT": BEARISH_KLINES},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert result == [], "昨日阴线应被过滤"

    @pytest.mark.asyncio
    async def test_sorts_by_market_cap_ascending(self) -> None:
        """组合：多个候选按市值从小到大排序。"""
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("MID", 30_000_000),
                make_alpha_token("SMALL", 5_000_000),
                make_alpha_token("LARGE", 45_000_000),
            ],
            symbols=[
                make_symbol_info_row("MID"),
                make_symbol_info_row("SMALL"),
                make_symbol_info_row("LARGE"),
            ],
            klines_by_symbol={
                "MIDUSDT": BULLISH_KLINES,
                "SMALLUSDT": BULLISH_KLINES,
                "LARGEUSDT": BULLISH_KLINES,
            },
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        caps = [i.market_cap for i in result]
        assert caps == sorted(caps), f"应按市值升序，实际 {caps}"
        assert [i.symbol for i in result] == ["SMALLUSDT", "MIDUSDT", "LARGEUSDT"]


class TestAlphaSourceTechnicalFieldsDefault:
    """关键不变量：source 输出的技术字段全为默认值（技术分析已剥离）。"""

    @pytest.mark.asyncio
    async def test_technical_fields_all_default(self) -> None:
        """纯增强不变量：source 不填任何技术字段，全为 None/False。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],
            symbols=[make_symbol_info_row("ABC")],
            klines_by_symbol={"ABCUSDT": BULLISH_KLINES},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        info = result[0]
        assert info.sma_200 is None
        assert info.price_vs_sma200_percent is None
        assert info.cross_signal is None
        assert info.cross_ago is None
        assert info.is_sideways_bottom is False
        assert info.volatility_10 is None


class TestAlphaSourceEmpty:
    """空值测试。"""

    @pytest.mark.asyncio
    async def test_no_alpha_tokens_returns_empty(self) -> None:
        """空值：无 Alpha 代币 -> []。"""
        client = FakeAlphaClient(alpha_tokens=[], symbols=[])
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert result == []


class TestAlphaSourceCarriesDeliveryDate:
    """下架预警数据流：source 应把 exchangeInfo 的 delivery_date 透传到 SymbolInfo。"""

    @pytest.mark.asyncio
    async def test_carries_sentinel_for_normal_perpetual(self) -> None:
        """正常路径：正常永续合约 -> info.delivery_date == 哨兵值。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],
            symbols=[make_symbol_info_row("ABC", delivery_date=4133404800000)],
            klines_by_symbol={"ABCUSDT": BULLISH_KLINES},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].delivery_date == 4133404800000, "正常永续应携带哨兵值"

    @pytest.mark.asyncio
    async def test_carries_concrete_date_for_delisting(self) -> None:
        """正常路径：即将下架 -> info.delivery_date == 具体下架时点。"""
        delisting_date = 1782637200000  # IPUSDT 式下架时点
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("DLST", 10_000_000)],
            symbols=[make_symbol_info_row("DLST", delivery_date=delisting_date)],
            klines_by_symbol={"DLSTUSDT": BULLISH_KLINES},
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].delivery_date == delisting_date, "即将下架应携带具体时点"

    @pytest.mark.asyncio
    async def test_mixed_delisting_dates_preserved(self) -> None:
        """组合：正常与即将下架并存，各自 delivery_date 正确保留。"""
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("NORM", 5_000_000),
                make_alpha_token("DLST", 10_000_000),
            ],
            symbols=[
                make_symbol_info_row("NORM", delivery_date=4133404800000),
                make_symbol_info_row("DLST", delivery_date=1782637200000),
            ],
            klines_by_symbol={
                "NORMUSDT": BULLISH_KLINES,
                "DLSTUSDT": BULLISH_KLINES,
            },
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        by_sym = {i.symbol: i for i in result}
        assert by_sym["NORMUSDT"].delivery_date == 4133404800000
        assert by_sym["DLSTUSDT"].delivery_date == 1782637200000
