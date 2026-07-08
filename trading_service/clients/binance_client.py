from __future__ import annotations

import logging
from typing import Any

import ccxt
import requests
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


def _parse_float(value: Any) -> float | None:
    """解析数值为 float。"""
    if value is None:
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def _parse_int(value: Any) -> int | None:
    """解析数值为 int。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None
class BinanceAlphaToken(BaseModel):
    """币安阿尔法代币信息。"""

    token_id: str = Field(alias="tokenId")
    chain_id: int | str | None = Field(alias="chainId")
    chain_icon_url: str | None = Field(alias="chainIconUrl", default=None)
    chain_name: str | None = Field(alias="chainName", default=None)
    contract_address: str = Field(alias="contractAddress")
    name: str
    symbol: str
    icon_url: str | None = Field(alias="iconUrl", default=None)
    price: str | float
    percent_change_24h: float | None = Field(alias="percentChange24h", default=None)
    volume_24h: str | float | None = Field(alias="volume24h", default=None)
    market_cap: float | None = Field(alias="marketCap", default=None)
    fdv: float | None = None
    liquidity: str | float | None = None
    total_supply: int | float | None = Field(alias="totalSupply", default=None)
    circulating_supply: int | float | None = Field(alias="circulatingSupply", default=None)
    holders: int | None = None
    decimals: int | None = None
    listing_cex: bool = Field(alias="listingCex", default=False)
    hot_tag: bool = Field(alias="hotTag", default=False)
    cex_coin_name: str = Field(alias="cexCoinName", default="")
    can_transfer: bool = Field(alias="canTransfer", default=False)
    denomination: int = 1
    offline: bool = False
    trade_decimal: int | None = Field(alias="tradeDecimal", default=None)
    alpha_id: str = Field(alias="alphaId")
    offsell: bool = False
    price_high_24h: str | float | None = Field(alias="priceHigh24h", default=None)
    price_low_24h: str | float | None = Field(alias="priceLow24h", default=None)
    count_24h: int | None = Field(alias="count24h", default=None)
    online_tge: bool = Field(alias="onlineTge", default=False)
    online_airdrop: bool = Field(alias="onlineAirdrop", default=False)
    score: int | None = None
    cex_off_display: bool = Field(alias="cexOffDisplay", default=False)
    stock_state: bool = Field(alias="stockState", default=False)
    listing_time: int | None = Field(alias="listingTime", default=None)
    mul_point: int = Field(alias="mulPoint", default=1)
    bn_exclusive_state: bool = Field(alias="bnExclusiveState", default=False)
    cex_states: int = Field(alias="cexStates", default=0)
    fully_delisted: bool = Field(alias="fullyDelisted", default=False)

    @field_validator(
        "percent_change_24h",
        "market_cap",
        "fdv",
        mode="before",
    )
    @classmethod
    def parse_float_fields(cls, v: object) -> float | None:
        return _parse_float(v)

    @field_validator(
        "total_supply",
        "circulating_supply",
        "holders",
        "decimals",
        "trade_decimal",
        "count_24h",
        "score",
        "listing_time",
        mode="before",
    )
    @classmethod
    def parse_int_fields(cls, v: object) -> int | None:
        return _parse_int(v)

    @field_validator("chain_id", mode="before")
    @classmethod
    def parse_chain_id(cls, v: Any) -> int | str | None:
        if v is None:
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return str(v)


class BinanceAlphaTokenListResponse(BaseModel):
    """币安阿尔法代币列表响应。"""

    code: str
    message: str | None
    message_detail: str | None = Field(alias="messageDetail")
    data: list[BinanceAlphaToken]
    success: bool


class BinanceFutureAsset(BaseModel):
    """合约资产信息。"""

    asset: str
    margin_available: bool = Field(alias="marginAvailable")
    auto_asset_exchange: str = Field(alias="autoAssetExchange")


class BinanceFutureSymbolFilter(BaseModel):
    """合约交易对过滤器。"""

    filter_type: str = Field(alias="filterType")
    min_price: str | None = Field(alias="minPrice", default=None)
    max_price: str | None = Field(alias="maxPrice", default=None)
    tick_size: str | None = Field(alias="tickSize", default=None)
    min_qty: str | None = Field(alias="minQty", default=None)
    max_qty: str | None = Field(alias="maxQty", default=None)
    step_size: str | None = Field(alias="stepSize", default=None)
    limit: int | None = None
    notional: str | None = None


class BinanceFutureSymbol(BaseModel):
    """合约交易对信息。"""

    symbol: str
    pair: str
    contract_type: str = Field(alias="contractType")
    delivery_date: int = Field(alias="deliveryDate")
    onboard_date: int = Field(alias="onboardDate")
    status: str
    maint_margin_percent: str = Field(alias="maintMarginPercent")
    required_margin_percent: str = Field(alias="requiredMarginPercent")
    base_asset: str = Field(alias="baseAsset")
    quote_asset: str = Field(alias="quoteAsset")
    margin_asset: str = Field(alias="marginAsset")
    price_precision: int = Field(alias="pricePrecision")
    quantity_precision: int = Field(alias="quantityPrecision")
    base_asset_precision: int = Field(alias="baseAssetPrecision")
    quote_precision: int = Field(alias="quotePrecision")
    underlying_type: str = Field(alias="underlyingType")
    underlying_sub_type: list[str] = Field(alias="underlyingSubType")
    trigger_protect: str = Field(alias="triggerProtect")
    liquidation_fee: str = Field(alias="liquidationFee")
    market_take_bound: str = Field(alias="marketTakeBound")
    max_move_order_limit: int | None = Field(alias="maxMoveOrderLimit", default=None)
    filters: list[BinanceFutureSymbolFilter]
    order_types: list[str] = Field(alias="orderTypes")
    time_in_force: list[str] = Field(alias="timeInForce")
    permission_sets: list[list[str]] | list[str] | None = Field(
        alias="permissionSets",
        default=None,
    )


class BinanceFutureRateLimit(BaseModel):
    """费率限制。"""

    interval: str
    interval_num: int = Field(alias="intervalNum")
    limit: int
    rate_limit_type: str = Field(alias="rateLimitType")


class BinanceFutureExchangeInfo(BaseModel):
    """币安合约交易所信息。"""

    exchange_filters: list[str] = Field(alias="exchangeFilters")
    rate_limits: list[BinanceFutureRateLimit] = Field(alias="rateLimits")
    server_time: int = Field(alias="serverTime")
    assets: list[BinanceFutureAsset]
    symbols: list[BinanceFutureSymbol]
    timezone: str


class BinanceFutureKline(BaseModel):
    """币安合约 K 线数据。"""

    open_time: int
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    close_time: int
    quote_volume: str
    trade_count: int
    taker_buy_base_volume: str
    taker_buy_quote_volume: str
    ignore: str

    @classmethod
    def from_list(cls, kline_data: list) -> "BinanceFutureKline":
        """从币安 API 返回的数组创建 K 线实例。

        Args:
            kline_data: [open_time, open, high, low, close, volume, close_time,
                         quote_volume, trade_count, taker_buy_base, taker_buy_quote, ignore]

        Returns:
            BinanceFutureKline: K 线数据实例
        """
        return cls(
            open_time=kline_data[0],
            open_price=kline_data[1],
            high_price=kline_data[2],
            low_price=kline_data[3],
            close_price=kline_data[4],
            volume=kline_data[5],
            close_time=kline_data[6],
            quote_volume=kline_data[7],
            trade_count=kline_data[8],
            taker_buy_base_volume=kline_data[9],
            taker_buy_quote_volume=kline_data[10],
            ignore=kline_data[11],
        )

    @property
    def open_price_float(self) -> float:
        """开盘价（数值型）。"""
        return float(self.open_price)

    @property
    def high_price_float(self) -> float:
        """最高价（数值型）。"""
        return float(self.high_price)

    @property
    def low_price_float(self) -> float:
        """最低价（数值型）。"""
        return float(self.low_price)

    @property
    def close_price_float(self) -> float:
        """收盘价（数值型）。"""
        return float(self.close_price)

    @property
    def volume_float(self) -> float:
        """成交量（基础货币，数值型）。"""
        return float(self.volume)

    @property
    def quote_volume_float(self) -> float:
        """成交额（计价货币，数值型）。"""
        return float(self.quote_volume)

    @property
    def taker_buy_base_volume_float(self) -> float:
        """主动买入量（基础货币，数值型）。"""
        return float(self.taker_buy_base_volume)

    @property
    def taker_buy_quote_volume_float(self) -> float:
        """主动买入额（计价货币，数值型）。"""
        return float(self.taker_buy_quote_volume)

    @property
    def is_up(self) -> bool:
        """是否上涨（收盘价 >= 开盘价）。"""
        return self.close_price_float >= self.open_price_float

    @property
    def is_down(self) -> bool:
        """是否下跌（收盘价 < 开盘价）。"""
        return self.close_price_float < self.open_price_float

    @property
    def price_change_percent_float(self) -> float:
        """涨跌幅百分比。

        Returns:
            float: 涨跌幅百分比，正数为涨，负数为跌
        """
        if self.open_price_float == 0:
            return 0.0
        return (
            (self.close_price_float - self.open_price_float)
            / self.open_price_float
            * 100
        )


class BinanceFutureTicker24hr(BaseModel):
    """币安合约 24 小时行情数据。"""

    symbol: str
    price_change: str = Field(alias="priceChange")
    price_change_percent: str = Field(alias="priceChangePercent")
    weighted_avg_price: str = Field(alias="weightedAvgPrice")
    last_price: str = Field(alias="lastPrice")
    last_qty: str = Field(alias="lastQty")
    open_price: str = Field(alias="openPrice")
    high_price: str = Field(alias="highPrice")
    low_price: str = Field(alias="lowPrice")
    volume: str
    quote_volume: str = Field(alias="quoteVolume")
    open_time: int = Field(alias="openTime")
    close_time: int = Field(alias="closeTime")
    first_id: int = Field(alias="firstId")
    last_id: int = Field(alias="lastId")
    count: int

    @property
    def price_change_float(self) -> float:
        """价格变动（数值型）。"""
        return float(self.price_change)

    @property
    def price_change_percent_float(self) -> float:
        """价格变动百分比（数值型）。"""
        return float(self.price_change_percent)

    @property
    def last_price_float(self) -> float:
        """最新价格（数值型）。"""
        return float(self.last_price)

    @property
    def volume_float(self) -> float:
        """成交量（基础货币，数值型）。"""
        return float(self.volume)

    @property
    def quote_volume_float(self) -> float:
        """成交额（计价货币，数值型）。"""
        return float(self.quote_volume)

    @property
    def high_price_float(self) -> float:
        """最高价（数值型）。"""
        return float(self.high_price)

    @property
    def low_price_float(self) -> float:
        """最低价（数值型）。"""
        return float(self.low_price)

    @property
    def open_price_float(self) -> float:
        """开盘价（数值型）。"""
        return float(self.open_price)

    @property
    def last_qty_float(self) -> float:
        """最新成交量（数值型）。"""
        return float(self.last_qty)

    @property
    def weighted_avg_price_float(self) -> float:
        """加权平均价（数值型）。"""
        return float(self.weighted_avg_price)


class BinanceClient:
    """币安 API 客户端。

    封装币安各类 API 接口：
    - 阿尔法代币列表（公开 API）
    - 合约市场数据（使用 ccxt）
    """

    BASE_URL = "https://www.binance.com/bapi"

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self._future_exchange: ccxt.binance | None = None

    @property
    def future_exchange(self) -> ccxt.binance:
        """获取币安合约交易所实例（懒加载）。"""
        if self._future_exchange is None:
            self._future_exchange = ccxt.binance(
                {
                    "enableRateLimit": True,
                    "timeout": self.timeout * 1000,
                    "options": {
                        "defaultType": "future",
                    },
                }
            )
        return self._future_exchange

    def _get(self, path: str, params: dict | None = None) -> dict:
        """发送 GET 请求。"""
        url = f"{self.BASE_URL}{path}"
        logger.debug(f"GET {url} params={params}")

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Response: {data.get('code')}, success={data.get('success')}")
            return data
        except requests.RequestException as e:
            logger.error(f"Binance API request failed: {e}")
            raise

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        """获取所有阿尔法代币列表。

        Returns:
            list[BinanceAlphaToken]: 阿尔法代币列表
        """
        path = "/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
        raw_data = self._get(path)
        response = BinanceAlphaTokenListResponse.model_validate(raw_data)

        if not response.success:
            logger.warning(f"Binance API returned success=False: {response.message}")

        logger.info(f"Fetched {len(response.data)} alpha tokens from Binance")
        return response.data

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        """获取币安合约交易所信息。

        包含所有交易对配置、费率限制、资产信息等。

        Returns:
            BinanceFutureExchangeInfo: 交易所信息
        """
        raw_data = self.future_exchange.fapiPublicGetExchangeInfo()
        return BinanceFutureExchangeInfo.model_validate(raw_data)

    def get_future_ticker_24hr(self, symbol: str | None = None) -> list[BinanceFutureTicker24hr]:
        """获取币安合约 24 小时行情数据。

        Args:
            symbol: 交易对符号（如 "BTCUSDT"）。不传则返回所有交易对。

        Returns:
            list[BinanceFutureTicker24hr]: 24小时行情数据列表
        """
        if symbol:
            raw_data = self.future_exchange.fapiPublicGetTicker24hr({"symbol": symbol})
            return [BinanceFutureTicker24hr.model_validate(raw_data)]
        else:
            raw_data_list = self.future_exchange.fapiPublicGetTicker24hr()
            return [BinanceFutureTicker24hr.model_validate(item) for item in raw_data_list]

    def get_future_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[BinanceFutureKline]:
        """获取币安合约 K 线数据。

        Args:
            symbol: 交易对符号（如 "BTCUSDT"）
            interval: K 线时间周期，可选值:
                分钟: 1m, 3m, 5m, 15m, 30m
                小时: 1h, 2h, 4h, 6h, 8h, 12h
                日/周/月: 1d, 3d, 1w, 1M
            limit: 获取的 K 线数量，默认 500，最大 1500
            start_time: 起始时间戳（毫秒），可选
            end_time: 结束时间戳（毫秒），可选

        Returns:
            list[BinanceFutureKline]: K 线数据列表，按时间升序排列
        """
        params: dict[str, object] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        raw_data = self.future_exchange.fapiPublicGetKlines(params)
        return [BinanceFutureKline.from_list(kline) for kline in raw_data]

    def close(self) -> None:
        """关闭会话。"""
        self.session.close()
        if self._future_exchange:
            self._future_exchange.close()

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object | None) -> None:
        self.close()
