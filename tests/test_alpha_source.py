"""测试 AlphaTokenSource（TDD 红阶段）。

AlphaTokenSource 是纯数据源：只做候选集构建（Alpha 代币 + 市值门槛 + 合约可交易），
不拉 K 线、不做阳线过滤。交易筛选由独立的 ISymbolFilter 完成。

关键断言：
1. 输出的 SymbolInfo klines 为空 dict -- 证明 source 不做技术分析
2. 基础筛选逻辑正确：市值超限/不可交易 -> 被过滤
3. 实现 ISymbolSource

使用 FakeClient + 构造内存数据，零网络。
"""
from __future__ import annotations

import inspect

import pytest

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceFutureExchangeInfo,
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


class FakeAlphaClient:
    """最小化 client：实现 AlphaTokenSource 用到的两个方法。"""

    def __init__(
        self,
        alpha_tokens: list[BinanceAlphaToken],
        symbols: list[BinanceFutureSymbol],
    ) -> None:
        self._alpha_tokens = alpha_tokens
        self._symbols = symbols

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        return self._alpha_tokens

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        return BinanceFutureExchangeInfo(
            exchangeFilters=[], rateLimits=[], serverTime=0,
            assets=[], symbols=self._symbols, timezone="UTC",
        )


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
    async def test_filters_below_cap_tradable(self) -> None:
        """正常路径：市值<5000万 + 可交易 -> 保留。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],
            symbols=[make_symbol_info_row("ABC")],
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
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert result == []

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
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        caps = [i.market_cap for i in result]
        assert caps == sorted(caps), f"应按市值升序，实际 {caps}"
        assert [i.symbol for i in result] == ["SMALLUSDT", "MIDUSDT", "LARGEUSDT"]


class TestAlphaSourceTechnicalFieldsDefault:
    """关键不变量：source 输出的 klines 为空 dict（source 不拉 K 线）。"""

    @pytest.mark.asyncio
    async def test_technical_fields_all_default(self) -> None:
        """纯增强不变量：source 不构建 klines DataFrame，klines 为空 dict。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],
            symbols=[make_symbol_info_row("ABC")],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        info = result[0]
        assert info.klines == {}, "AlphaTokenSource 不应构建 klines DataFrame"


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
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        by_sym = {i.symbol: i for i in result}
        assert by_sym["NORMUSDT"].delivery_date == 4133404800000
        assert by_sym["DLSTUSDT"].delivery_date == 1782637200000
