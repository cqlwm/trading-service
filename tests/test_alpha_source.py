"""测试 AlphaTokenSource（TDD 红阶段）。

AlphaTokenSource 是纯数据源：只做候选集构建（Alpha 代币 + 市值门槛 + 合约可交易），
不拉 K 线、不做阳线过滤。交易筛选由独立的 ISymbolFilter 完成。

关键断言：
1. 输出的 SymbolInfo klines 为空 dict -- 证明 source 不做技术分析
2. 基础筛选逻辑正确：市值超限/不可交易 -> 被过滤
3. 实现 ISymbolSource
4. 市值 = circulating_supply × 合约最新价（last_price）；supply 缺失降级用现货 marketCap

使用 FakeClient + 构造内存数据，零网络。
"""
from __future__ import annotations

import inspect

import pytest

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceFutureExchangeInfo,
    BinanceFutureSymbol,
    BinanceFutureTicker24hr,
)
from trading_service.pickers.pipeline import ISymbolSource
from trading_service.pickers.symbol_picker import AlphaTokenSource


def make_alpha_token(
    symbol: str,
    market_cap: float | None,
    circulating_supply: int | float | None = None,
) -> BinanceAlphaToken:
    """构造一个 Alpha 代币（用 API alias 字段名，仅填充 source 用到 + 必填字段）。"""
    data: dict[str, object] = {
        "tokenId": f"id-{symbol}",
        "chainId": 1,
        "contractAddress": f"0x{symbol}",
        "name": symbol,
        "symbol": symbol,
        "price": "1.0",
        "alphaId": f"alpha-{symbol}",
        "marketCap": market_cap,
    }
    if circulating_supply is not None:
        data["circulatingSupply"] = circulating_supply
    return BinanceAlphaToken.model_validate(data)


def make_ticker(symbol: str, last_price: float) -> BinanceFutureTicker24hr:
    """构造一个合约 24h ticker（仅填充 source 用到的 last_price 字段）。"""
    return BinanceFutureTicker24hr.model_validate({
        "symbol": symbol,
        "priceChange": "0",
        "priceChangePercent": "0",
        "weightedAvgPrice": "0",
        "lastPrice": str(last_price),
        "lastQty": "0",
        "openPrice": "0",
        "highPrice": "0",
        "lowPrice": "0",
        "volume": "0",
        "quoteVolume": "0",
        "openTime": 0,
        "closeTime": 0,
        "firstId": 0,
        "lastId": 0,
        "count": 0,
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
    """最小化 client：实现 AlphaTokenSource 用到的三个方法。"""

    def __init__(
        self,
        alpha_tokens: list[BinanceAlphaToken],
        symbols: list[BinanceFutureSymbol],
        tickers: list[BinanceFutureTicker24hr] | None = None,
    ) -> None:
        self._alpha_tokens = alpha_tokens
        self._symbols = symbols
        self._tickers = tickers or []

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        return self._alpha_tokens

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        return BinanceFutureExchangeInfo(
            exchangeFilters=[], rateLimits=[], serverTime=0,
            assets=[], symbols=self._symbols, timezone="UTC",
        )

    def get_future_ticker_24hr(self, symbol: str | None = None) -> list[BinanceFutureTicker24hr]:
        """返回注入的合约 ticker（测试用，不区分 symbol 过滤）。"""
        if symbol is None:
            return self._tickers
        return [t for t in self._tickers if t.symbol == symbol]


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


class TestAlphaSourceContractMarketCap:
    """合约市值计算测试：市值 = circulating_supply × 合约最新价。

    核心改造：不再直接用现货 marketCap，而是用流通量乘以合约 ticker 的 last_price。
    circulating_supply 为 None 时，降级用现货 marketCap 兜底。
    """

    @pytest.mark.asyncio
    async def test_market_cap_equals_supply_times_contract_price(self) -> None:
        """正常路径：市值 = circulating_supply × 合约 last_price。"""
        # 流通量 1000万，合约价 3.0 -> 市值 3000万 < 5000万 -> 保留
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 99_000_000, circulating_supply=10_000_000)],
            symbols=[make_symbol_info_row("ABC")],
            tickers=[make_ticker("ABCUSDT", 3.0)],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].market_cap == 30_000_000.0, \
            f"市值应为 1000万 × 3.0 = 3000万，实际 {result[0].market_cap}"

    @pytest.mark.asyncio
    async def test_falls_back_to_spot_market_cap_when_supply_none(self) -> None:
        """降级路径：circulating_supply 为 None -> 用现货 marketCap 兜底。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000)],  # 无 circulating_supply
            symbols=[make_symbol_info_row("ABC")],
            tickers=[make_ticker("ABCUSDT", 3.0)],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].market_cap == 10_000_000, \
            f"supply 缺失应降级用现货 marketCap，实际 {result[0].market_cap}"

    @pytest.mark.asyncio
    async def test_filters_above_cap_using_contract_price(self) -> None:
        """边界：合约价算出的市值 >= 5000万 -> 过滤掉（即使现货 marketCap 很小）。"""
        # 现货 marketCap 只有 1000万，但流通量 2000万 × 合约价 3.0 = 6000万 -> 超限
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("BIG", 10_000_000, circulating_supply=20_000_000),
                make_alpha_token("SMALL", 10_000_000, circulating_supply=5_000_000),
            ],
            symbols=[make_symbol_info_row("BIG"), make_symbol_info_row("SMALL")],
            tickers=[make_ticker("BIGUSDT", 3.0), make_ticker("SMALLUSDT", 3.0)],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert [i.symbol for i in result] == ["SMALLUSDT"], \
            "BIG 合约市值 6000万应被过滤，只留 SMALL(1500万)"

    @pytest.mark.asyncio
    async def test_batch_fetches_all_tickers_once(self) -> None:
        """组合：多个候选币，应批量拉全部 ticker 后按 symbol 匹配，不逐个请求。"""
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("AAA", 99_000_000, circulating_supply=1_000_000),
                make_alpha_token("BBB", 99_000_000, circulating_supply=2_000_000),
            ],
            symbols=[make_symbol_info_row("AAA"), make_symbol_info_row("BBB")],
            tickers=[make_ticker("AAAUSDT", 10.0), make_ticker("BBBUSDT", 20.0)],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        by_sym = {i.symbol: i.market_cap for i in result}
        assert by_sym["AAAUSDT"] == 10_000_000.0, "100万 × 10 = 1000万"
        assert by_sym["BBBUSDT"] == 40_000_000.0, "200万 × 20 = 4000万"

    @pytest.mark.asyncio
    async def test_missing_ticker_falls_back_to_spot(self) -> None:
        """降级路径：合约 ticker 缺失（无最新价）-> 用现货 marketCap 兜底。"""
        # 有 circulating_supply 但合约无 ticker -> 无法算合约市值 -> 降级用现货
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("ABC", 10_000_000, circulating_supply=5_000_000)],
            symbols=[make_symbol_info_row("ABC")],
            tickers=[],  # 该合约无 ticker
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        assert len(result) == 1
        assert result[0].market_cap == 10_000_000, \
            f"合约价缺失应降级用现货 marketCap，实际 {result[0].market_cap}"

    @pytest.mark.asyncio
    async def test_sorts_by_contract_market_cap_ascending(self) -> None:
        """组合：按合约市值（非现货）升序排序。"""
        # 现货市值都是 99M（应被忽略），合约市值不同
        client = FakeAlphaClient(
            alpha_tokens=[
                make_alpha_token("MID", 99_000_000, circulating_supply=10_000_000),   # ×3 = 30M
                make_alpha_token("SMALL", 99_000_000, circulating_supply=1_000_000),  # ×3 = 3M
                make_alpha_token("LARGE", 99_000_000, circulating_supply=15_000_000), # ×3 = 45M
            ],
            symbols=[make_symbol_info_row("MID"), make_symbol_info_row("SMALL"), make_symbol_info_row("LARGE")],
            tickers=[
                make_ticker("MIDUSDT", 3.0),
                make_ticker("SMALLUSDT", 3.0),
                make_ticker("LARGEUSDT", 3.0),
            ],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()

        caps = [i.market_cap for i in result]
        assert caps == sorted(caps), f"应按合约市值升序，实际 {caps}"
        assert [i.symbol for i in result] == ["SMALLUSDT", "MIDUSDT", "LARGEUSDT"]

    @pytest.mark.asyncio
    async def test_untradable_contract_not_computed(self) -> None:
        """隔离：无对应可交易合约的代币 -> 直接过滤，不参与市值计算。"""
        client = FakeAlphaClient(
            alpha_tokens=[make_alpha_token("NOCONTRACT", 99_000_000, circulating_supply=1_000_000)],
            symbols=[],  # 无可交易合约
            tickers=[make_ticker("NOCONTRACTUSDT", 3.0)],
        )
        source = AlphaTokenSource(client=client)
        result = await source.fetch()
        assert result == [], "无可交易合约的代币应被过滤"
