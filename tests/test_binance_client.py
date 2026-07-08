"""BinanceClient 测试。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceAlphaTokenListResponse,
    BinanceClient,
    BinanceFutureAsset,
    BinanceFutureExchangeInfo,
    BinanceFutureRateLimit,
    BinanceFutureSymbol,
    BinanceFutureSymbolFilter,
    BinanceFutureKline,
    BinanceFutureTicker24hr,
    _parse_float,
    _parse_int,
)


class MockResponse:
    """模拟 HTTP 响应。"""

    def __init__(
        self,
        json_data: dict | None = None,
        status_code: int = 200,
        raise_exception: Exception | None = None,
    ) -> None:
        self._json_data = json_data or {}
        self.status_code = status_code
        self._raise_exception = raise_exception

    def json(self) -> dict:
        return self._json_data

    def raise_for_status(self) -> None:
        if self._raise_exception:
            raise self._raise_exception


class TestHelperFunctions:
    """测试辅助函数。"""

    def test_parse_float_with_none(self) -> None:
        """解析 None 应该返回 None。"""
        assert _parse_float(None) is None

    def test_parse_float_with_float(self) -> None:
        """解析 float 应该直接返回。"""
        assert _parse_float(123.45) == 123.45

    def test_parse_float_with_int(self) -> None:
        """解析 int 应该转换为 float。"""
        assert _parse_int(123) == 123

    def test_parse_float_with_string(self) -> None:
        """解析字符串形式的数字。"""
        assert _parse_float("123.45") == 123.45
        assert _parse_float("123") == 123.0

    def test_parse_float_with_invalid_string(self) -> None:
        """解析无效字符串应该返回 None。"""
        assert _parse_float("invalid") is None

    def test_parse_int_with_none(self) -> None:
        """解析 None 应该返回 None。"""
        assert _parse_int(None) is None

    def test_parse_int_with_int(self) -> None:
        """解析 int 应该直接返回。"""
        assert _parse_int(123) == 123

    def test_parse_int_with_float(self) -> None:
        """解析 float 应该取整。"""
        assert _parse_int(123.9) == 123

    def test_parse_int_with_string(self) -> None:
        """解析字符串形式的数字。"""
        assert _parse_int("123") == 123
        assert _parse_int("123.9") == 123

    def test_parse_int_with_invalid_string(self) -> None:
        """解析无效字符串应该返回 None。"""
        assert _parse_int("invalid") is None


class TestBinanceAlphaTokenModel:
    """测试 BinanceAlphaToken Pydantic 模型。"""

    def test_parse_normal_token(self) -> None:
        """解析正常格式的代币数据。"""
        raw_data = {
            "tokenId": "abc123",
            "chainId": 56,
            "chainIconUrl": "http://example.com/icon.png",
            "chainName": "BSC",
            "contractAddress": "0x123",
            "name": "Test Token",
            "symbol": "TEST",
            "iconUrl": "http://example.com/token.png",
            "price": "1.23",
            "percentChange24h": "-5.5",
            "volume24h": "100000",
            "marketCap": "500000",
            "fdv": "1000000",
            "liquidity": "50000",
            "totalSupply": "1000000",
            "circulatingSupply": "500000",
            "holders": 1000,
            "decimals": 18,
            "listingCex": False,
            "hotTag": True,
            "cexCoinName": "",
            "canTransfer": True,
            "denomination": 1,
            "offline": False,
            "tradeDecimal": 8,
            "alphaId": "ALPHA_001",
            "offsell": False,
            "priceHigh24h": "1.5",
            "priceLow24h": "1.0",
            "count24h": 500,
            "onlineTge": False,
            "onlineAirdrop": True,
            "score": 95,
            "cexOffDisplay": False,
            "stockState": True,
            "listingTime": 1782979200000,
            "mulPoint": 1,
            "bnExclusiveState": True,
            "cexStates": 0,
            "fullyDelisted": False,
        }

        token = BinanceAlphaToken.model_validate(raw_data)

        assert token.token_id == "abc123"
        assert token.chain_id == 56
        assert token.symbol == "TEST"
        assert token.name == "Test Token"
        assert token.percent_change_24h == -5.5
        assert token.market_cap == 500000.0
        assert token.holders == 1000
        assert token.hot_tag is True
        assert token.bn_exclusive_state is True

    def test_parse_token_with_string_chain_id(self) -> None:
        """解析 chainId 为字符串形式的代币（如 CT_501）。"""
        raw_data = {
            "tokenId": "abc123",
            "chainId": "CT_501",
            "chainName": None,
            "contractAddress": "0x123",
            "name": "Test Token",
            "symbol": "TEST",
            "price": "1.23",
            "alphaId": "ALPHA_001",
        }

        token = BinanceAlphaToken.model_validate(raw_data)

        assert token.chain_id == "CT_501"
        assert token.chain_name is None

    def test_parse_token_with_null_fields(self) -> None:
        """解析包含 null 值的代币数据。"""
        raw_data = {
            "tokenId": "abc123",
            "chainId": 56,
            "contractAddress": "0x123",
            "name": "Test Token",
            "symbol": "TEST",
            "price": "1.23",
            "alphaId": "ALPHA_001",
            "holders": None,
            "liquidity": None,
            "count24h": None,
        }

        token = BinanceAlphaToken.model_validate(raw_data)

        assert token.holders is None
        assert token.liquidity is None
        assert token.count_24h is None

    def test_parse_token_with_decimal_supply(self) -> None:
        """解析带小数的供应量数据。"""
        raw_data = {
            "tokenId": "abc123",
            "chainId": 56,
            "contractAddress": "0x123",
            "name": "Test Token",
            "symbol": "TEST",
            "price": "1.23",
            "alphaId": "ALPHA_001",
            "totalSupply": "1234567.89",
            "circulatingSupply": "987654.32",
        }

        token = BinanceAlphaToken.model_validate(raw_data)

        assert token.total_supply == 1234567
        assert token.circulating_supply == 987654


class TestBinanceAlphaTokenListResponseModel:
    """测试 BinanceAlphaTokenListResponse 模型。"""

    def test_parse_success_response(self) -> None:
        """解析成功响应。"""
        raw_data = {
            "code": "000000",
            "message": None,
            "messageDetail": None,
            "data": [
                {
                    "tokenId": "abc123",
                    "chainId": 56,
                    "contractAddress": "0x123",
                    "name": "Test Token 1",
                    "symbol": "TEST1",
                    "price": "1.23",
                    "alphaId": "ALPHA_001",
                },
                {
                    "tokenId": "def456",
                    "chainId": 1,
                    "contractAddress": "0x456",
                    "name": "Test Token 2",
                    "symbol": "TEST2",
                    "price": "2.34",
                    "alphaId": "ALPHA_002",
                },
            ],
            "success": True,
        }

        response = BinanceAlphaTokenListResponse.model_validate(raw_data)

        assert response.success is True
        assert len(response.data) == 2
        assert response.data[0].symbol == "TEST1"
        assert response.data[1].symbol == "TEST2"

    def test_parse_empty_response(self) -> None:
        """解析空数据响应。"""
        raw_data = {
            "code": "000000",
            "message": None,
            "messageDetail": None,
            "data": [],
            "success": True,
        }

        response = BinanceAlphaTokenListResponse.model_validate(raw_data)

        assert response.success is True
        assert len(response.data) == 0


class TestBinanceFutureModels:
    """测试合约相关的 Pydantic 模型。"""

    def test_ticker_24hr_model(self) -> None:
        """测试 24 小时行情数据模型。"""
        raw_data = {
            "symbol": "BTCUSDT",
            "priceChange": "-94.99999800",
            "priceChangePercent": "-95.960",
            "weightedAvgPrice": "0.29628482",
            "lastPrice": "4.00000200",
            "lastQty": "200.00000000",
            "openPrice": "99.00000000",
            "highPrice": "100.00000000",
            "lowPrice": "0.10000000",
            "volume": "8913.30000000",
            "quoteVolume": "15.30000000",
            "openTime": 1499783499040,
            "closeTime": 1499869899040,
            "firstId": 28385,
            "lastId": 28460,
            "count": 76,
        }

        ticker = BinanceFutureTicker24hr.model_validate(raw_data)

        assert ticker.symbol == "BTCUSDT"
        assert ticker.price_change_percent_float == -95.96
        assert ticker.last_price_float == 4.000002
        assert ticker.volume_float == 8913.3
        assert ticker.count == 76
        assert ticker.high_price_float == 100.0
        assert ticker.low_price_float == 0.1

    def test_exchange_info_asset_model(self) -> None:
        """测试资产信息模型。"""
        raw_data = {
            "asset": "USDT",
            "marginAvailable": True,
            "autoAssetExchange": "-10000",
        }

        asset = BinanceFutureAsset.model_validate(raw_data)

        assert asset.asset == "USDT"
        assert asset.margin_available is True
        assert asset.auto_asset_exchange == "-10000"

    def test_exchange_info_rate_limit_model(self) -> None:
        """测试费率限制模型。"""
        raw_data = {
            "interval": "MINUTE",
            "intervalNum": 1,
            "limit": 2400,
            "rateLimitType": "REQUEST_WEIGHT",
        }

        rate_limit = BinanceFutureRateLimit.model_validate(raw_data)

        assert rate_limit.interval == "MINUTE"
        assert rate_limit.interval_num == 1
        assert rate_limit.limit == 2400
        assert rate_limit.rate_limit_type == "REQUEST_WEIGHT"

    def test_exchange_info_symbol_filter_model(self) -> None:
        """测试交易对过滤器模型。"""
        # PRICE_FILTER
        raw_price = {
            "filterType": "PRICE_FILTER",
            "minPrice": "556.80",
            "maxPrice": "4529764",
            "tickSize": "0.10",
        }
        price_filter = BinanceFutureSymbolFilter.model_validate(raw_price)
        assert price_filter.filter_type == "PRICE_FILTER"
        assert price_filter.min_price == "556.80"

        # LOT_SIZE
        raw_lot = {
            "filterType": "LOT_SIZE",
            "minQty": "0.001",
            "maxQty": "1000",
            "stepSize": "0.001",
        }
        lot_filter = BinanceFutureSymbolFilter.model_validate(raw_lot)
        assert lot_filter.filter_type == "LOT_SIZE"
        assert lot_filter.step_size == "0.001"

        # MAX_NUM_ORDERS
        raw_max = {
            "filterType": "MAX_NUM_ORDERS",
            "limit": 200,
        }
        max_filter = BinanceFutureSymbolFilter.model_validate(raw_max)
        assert max_filter.filter_type == "MAX_NUM_ORDERS"
        assert max_filter.limit == 200

        # MIN_NOTIONAL
        raw_notional = {
            "filterType": "MIN_NOTIONAL",
            "notional": "50",
        }
        notional_filter = BinanceFutureSymbolFilter.model_validate(raw_notional)
        assert notional_filter.filter_type == "MIN_NOTIONAL"
        assert notional_filter.notional == "50"

    def test_exchange_info_symbol_model(self) -> None:
        """测试交易对信息模型。"""
        raw_data = {
            "symbol": "BTCUSDT",
            "pair": "BTCUSDT",
            "contractType": "PERPETUAL",
            "deliveryDate": 4133404800000,
            "onboardDate": 1567965300000,
            "status": "TRADING",
            "maintMarginPercent": "2.5000",
            "requiredMarginPercent": "5.0000",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "marginAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 3,
            "baseAssetPrecision": 8,
            "quotePrecision": 8,
            "underlyingType": "COIN",
            "underlyingSubType": ["PoW"],
            "triggerProtect": "0.0500",
            "liquidationFee": "0.012500",
            "marketTakeBound": "0.05",
            "maxMoveOrderLimit": 10000,
            "filters": [
                {"filterType": "PRICE_FILTER", "minPrice": "556.80"},
                {"filterType": "LOT_SIZE", "minQty": "0.001"},
            ],
            "orderTypes": ["LIMIT", "MARKET"],
            "timeInForce": ["GTC", "IOC", "FOK"],
            "permissionSets": ["GRID", "COPY"],
        }

        symbol = BinanceFutureSymbol.model_validate(raw_data)

        assert symbol.symbol == "BTCUSDT"
        assert symbol.contract_type == "PERPETUAL"
        assert symbol.status == "TRADING"
        assert symbol.price_precision == 2
        assert symbol.quantity_precision == 3
        assert symbol.maint_margin_percent == "2.5000"
        assert len(symbol.filters) == 2
        assert symbol.order_types == ["LIMIT", "MARKET"]
        assert symbol.permission_sets == ["GRID", "COPY"]

    def test_exchange_info_full_model(self) -> None:
        """测试完整的交易所信息模型。"""
        raw_data = {
            "exchangeFilters": [""],
            "rateLimits": [
                {
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 2400,
                    "rateLimitType": "REQUEST_WEIGHT",
                }
            ],
            "serverTime": 1565613908500,
            "assets": [
                {"asset": "BTC", "marginAvailable": True, "autoAssetExchange": "-0.10"}
            ],
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "pair": "BTCUSDT",
                    "contractType": "PERPETUAL",
                    "deliveryDate": 4133404800000,
                    "onboardDate": 1598252400000,
                    "status": "TRADING",
                    "maintMarginPercent": "2.5000",
                    "requiredMarginPercent": "5.0000",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                    "pricePrecision": 2,
                    "quantityPrecision": 0,
                    "baseAssetPrecision": 8,
                    "quotePrecision": 8,
                    "underlyingType": "COIN",
                    "underlyingSubType": ["STORAGE"],
                    "triggerProtect": "0.15",
                    "liquidationFee": "0.010000",
                    "marketTakeBound": "0.30",
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "maxPrice": "300",
                            "minPrice": "0.0001",
                            "tickSize": "0.0001",
                        }
                    ],
                    "orderTypes": ["LIMIT"],
                    "timeInForce": ["GTC"],
                    "permissionSets": [["GRID"]],
                }
            ],
            "timezone": "UTC",
        }

        info = BinanceFutureExchangeInfo.model_validate(raw_data)

        assert info.timezone == "UTC"
        assert info.server_time == 1565613908500
        assert len(info.assets) == 1
        assert len(info.symbols) == 1
        assert len(info.rate_limits) == 1
        assert info.rate_limits[0].limit == 2400


    def test_kline_model_from_list(self) -> None:
        """测试 K 线模型从数组创建。"""
        raw_kline = [
            1499783499040,  # open_time
            "99.00000000",  # open
            "100.00000000",  # high
            "0.10000000",  # low
            "4.00000200",  # close
            "8913.30000000",  # volume
            1499869899040,  # close_time
            "15.30000000",  # quote_volume
            76,  # trade_count
            "4500.12345678",  # taker_buy_base
            "50000.12345678",  # taker_buy_quote
            "0",  # ignore
        ]

        kline = BinanceFutureKline.from_list(raw_kline)

        assert kline.open_time == 1499783499040
        assert kline.open_price == "99.00000000"
        assert kline.high_price == "100.00000000"
        assert kline.low_price == "0.10000000"
        assert kline.close_price == "4.00000200"
        assert kline.volume == "8913.30000000"
        assert kline.close_time == 1499869899040
        assert kline.quote_volume == "15.30000000"
        assert kline.trade_count == 76
        assert kline.taker_buy_base_volume == "4500.12345678"
        assert kline.taker_buy_quote_volume == "50000.12345678"
        assert kline.ignore == "0"

    def test_kline_model_float_properties(self) -> None:
        """测试 K 线模型的数值型属性。"""
        raw_kline = [
            1499783499040,
            "62000.50",
            "62500.00",
            "61800.25",
            "62350.75",
            "1000.5",
            1499869899040,
            "62500000.0",
            50000,
            "500.25",
            "31250000.0",
            "0",
        ]

        kline = BinanceFutureKline.from_list(raw_kline)

        assert kline.open_price_float == 62000.50
        assert kline.high_price_float == 62500.00
        assert kline.low_price_float == 61800.25
        assert kline.close_price_float == 62350.75
        assert kline.volume_float == 1000.5
        assert kline.quote_volume_float == 62500000.0
        assert kline.taker_buy_base_volume_float == 500.25
        assert kline.taker_buy_quote_volume_float == 31250000.0

    def test_kline_model_is_up_down(self) -> None:
        """测试 K 线涨跌判断。"""
        # 阳线（收盘价 >= 开盘价）
        bull_kline = [
            1499783499040, "100.0", "105.0", "95.0", "102.0",
            "1000", 1499869899040, "100000", 100, "500", "50000", "0"
        ]
        kline1 = BinanceFutureKline.from_list(bull_kline)
        assert kline1.is_up is True
        assert kline1.is_down is False

        # 阴线（收盘价 < 开盘价）
        bear_kline = [
            1499783499040, "100.0", "105.0", "95.0", "98.0",
            "1000", 1499869899040, "100000", 100, "500", "50000", "0"
        ]
        kline2 = BinanceFutureKline.from_list(bear_kline)
        assert kline2.is_up is False
        assert kline2.is_down is True

        # 十字星（收盘价 == 开盘价）
        doji_kline = [
            1499783499040, "100.0", "105.0", "95.0", "100.0",
            "1000", 1499869899040, "100000", 100, "500", "50000", "0"
        ]
        kline3 = BinanceFutureKline.from_list(doji_kline)
        assert kline3.is_up is True  # 平盘算上涨
        assert kline3.is_down is False

class TestBinanceClient:
    """测试 BinanceClient。"""

    def test_client_initialization(self) -> None:
        """测试客户端初始化。"""
        client = BinanceClient(timeout=15)

        assert client.timeout == 15
        assert client.BASE_URL == "https://www.binance.com/bapi"

    def test_client_context_manager(self) -> None:
        """测试上下文管理器协议。"""
        with BinanceClient() as client:
            assert client is not None
            assert client.session is not None

    def test_future_exchange_lazy_init(self) -> None:
        """测试合约交易所实例懒加载。"""
        client = BinanceClient()
        assert client._future_exchange is None
        exchange = client.future_exchange
        assert exchange is not None
        assert client._future_exchange is not None
        # 第二次调用应该返回同一个实例
        assert client.future_exchange is exchange

    def test_get_alpha_tokens_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试成功获取阿尔法代币列表。"""
        mock_response_data = {
            "code": "000000",
            "message": None,
            "messageDetail": None,
            "data": [
                {
                    "tokenId": "abc123",
                    "chainId": 56,
                    "contractAddress": "0x123",
                    "name": "Test Token",
                    "symbol": "TEST",
                    "price": "1.23",
                    "alphaId": "ALPHA_001",
                    "marketCap": 500000,
                    "percentChange24h": -5.5,
                },
            ],
            "success": True,
        }

        def mock_get(*args, **kwargs) -> MockResponse:  # noqa: ANN002, ANN003
            return MockResponse(json_data=mock_response_data)

        monkeypatch.setattr(requests.Session, "get", mock_get)

        client = BinanceClient()
        tokens = client.get_alpha_tokens()

        assert len(tokens) == 1
        assert tokens[0].symbol == "TEST"
        assert tokens[0].market_cap == 500000.0
        assert tokens[0].percent_change_24h == -5.5

    def test_get_alpha_tokens_request_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试网络请求异常。"""

        def mock_get(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise requests.RequestException("Network error")

        monkeypatch.setattr(requests.Session, "get", mock_get)

        client = BinanceClient()

        with pytest.raises(requests.RequestException, match="Network error"):
            client.get_alpha_tokens()

    def test_get_alpha_tokens_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试 HTTP 错误（如 404, 500）。"""

        def mock_get(*args, **kwargs) -> MockResponse:  # noqa: ANN002, ANN003
            return MockResponse(
                status_code=500,
                raise_exception=requests.HTTPError("500 Server Error"),
            )

        monkeypatch.setattr(requests.Session, "get", mock_get)

        client = BinanceClient()

        with pytest.raises(requests.HTTPError, match="500 Server Error"):
            client.get_alpha_tokens()

    def test_get_alpha_tokens_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试请求超时。"""

        def mock_get(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise requests.Timeout("Request timed out")

        monkeypatch.setattr(requests.Session, "get", mock_get)

        client = BinanceClient()

        with pytest.raises(requests.Timeout, match="Request timed out"):
            client.get_alpha_tokens()

    def test_get_alpha_tokens_connection_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试连接错误。"""

        def mock_get(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise requests.ConnectionError("Connection failed")

        monkeypatch.setattr(requests.Session, "get", mock_get)

        client = BinanceClient()

        with pytest.raises(requests.ConnectionError, match="Connection failed"):
            client.get_alpha_tokens()

    def test_get_future_exchange_info_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取交易所信息（mock 版本）。"""
        client = BinanceClient()

        mock_exchange = MagicMock()
        mock_exchange.fapiPublicGetExchangeInfo.return_value = {
            "exchangeFilters": [""],
            "rateLimits": [
                {
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": 2400,
                    "rateLimitType": "REQUEST_WEIGHT",
                }
            ],
            "serverTime": 1782979200000,
            "assets": [
                {"asset": "BTC", "marginAvailable": True, "autoAssetExchange": "-0.10"}
            ],
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "pair": "BTCUSDT",
                    "contractType": "PERPETUAL",
                    "deliveryDate": 4133404800000,
                    "onboardDate": 1598252400000,
                    "status": "TRADING",
                    "maintMarginPercent": "2.5000",
                    "requiredMarginPercent": "5.0000",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                    "pricePrecision": 2,
                    "quantityPrecision": 0,
                    "baseAssetPrecision": 8,
                    "quotePrecision": 8,
                    "underlyingType": "COIN",
                    "underlyingSubType": ["STORAGE"],
                    "triggerProtect": "0.15",
                    "liquidationFee": "0.010000",
                    "marketTakeBound": "0.30",
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "maxPrice": "300",
                            "minPrice": "0.0001",
                            "tickSize": "0.0001",
                        }
                    ],
                    "orderTypes": ["LIMIT"],
                    "timeInForce": ["GTC"],
                    "permissionSets": [["GRID"]],
                }
            ],
            "timezone": "UTC",
        }

        monkeypatch.setattr(client, "_future_exchange", mock_exchange)

        info = client.get_future_exchange_info()

        assert info.timezone == "UTC"
        assert info.server_time == 1782979200000
        assert len(info.assets) == 1
        assert len(info.symbols) == 1
        mock_exchange.fapiPublicGetExchangeInfo.assert_called_once()

    def test_get_future_ticker_24hr_all_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取所有交易对 24 小时行情（mock 版本）。"""
        client = BinanceClient()

        mock_exchange = MagicMock()
        mock_exchange.fapiPublicGetTicker24hr.return_value = [
            {
                "symbol": "BTCUSDT",
                "priceChange": "-1176.70",
                "priceChangePercent": "-1.860",
                "weightedAvgPrice": "63104.64",
                "lastPrice": "62084.50",
                "lastQty": "0.016",
                "openPrice": "63261.20",
                "highPrice": "64234.10",
                "lowPrice": "61708.20",
                "volume": "195371.752",
                "quoteVolume": "12328863584.19",
                "openTime": 1783417680000,
                "closeTime": 1783504091808,
                "firstId": 7876382803,
                "lastId": 7880970214,
                "count": 4580865,
            },
            {
                "symbol": "ETHUSDT",
                "priceChange": "-50.0",
                "priceChangePercent": "-2.5",
                "weightedAvgPrice": "2000.0",
                "lastPrice": "1950.0",
                "lastQty": "1.0",
                "openPrice": "2000.0",
                "highPrice": "2050.0",
                "lowPrice": "1900.0",
                "volume": "100000",
                "quoteVolume": "200000000",
                "openTime": 1783417680000,
                "closeTime": 1783504091808,
                "firstId": 123,
                "lastId": 456,
                "count": 789,
            },
        ]

        monkeypatch.setattr(client, "_future_exchange", mock_exchange)

        tickers = client.get_future_ticker_24hr()

        assert len(tickers) == 2
        assert tickers[0].symbol == "BTCUSDT"
        assert tickers[1].symbol == "ETHUSDT"
        assert tickers[0].price_change_percent_float == -1.860
        assert tickers[0].last_price_float == 62084.50
        assert tickers[0].count == 4580865

    def test_get_future_ticker_24hr_single_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取单个交易对 24 小时行情（mock 版本）。"""
        client = BinanceClient()

        mock_exchange = MagicMock()
        mock_exchange.fapiPublicGetTicker24hr.return_value = {
            "symbol": "BTCUSDT",
            "priceChange": "-1176.70",
            "priceChangePercent": "-1.860",
            "weightedAvgPrice": "63104.64",
            "lastPrice": "62084.50",
            "lastQty": "0.016",
            "openPrice": "63261.20",
            "highPrice": "64234.10",
            "lowPrice": "61708.20",
            "volume": "195371.752",
            "quoteVolume": "12328863584.19",
            "openTime": 1783417680000,
            "closeTime": 1783504091808,
            "firstId": 7876382803,
            "lastId": 7880970214,
            "count": 4580865,
        }

        monkeypatch.setattr(client, "_future_exchange", mock_exchange)

        tickers = client.get_future_ticker_24hr(symbol="BTCUSDT")

        assert len(tickers) == 1
        assert tickers[0].symbol == "BTCUSDT"
        assert tickers[0].last_price_float == 62084.50
        mock_exchange.fapiPublicGetTicker24hr.assert_called_once_with({"symbol": "BTCUSDT"})


    def test_get_future_klines_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取 K 线数据（mock 版本）。"""
        client = BinanceClient()

        mock_exchange = MagicMock()
        mock_exchange.fapiPublicGetKlines.return_value = [
            [
                1499783499040, "62000.00", "62500.00", "61500.00", "62250.00",
                "1000.5", 1499869899040, "62500000.0", 50000, "500.25", "31250000.0", "0"
            ],
            [
                1499869899040, "62250.00", "63000.00", "62000.00", "62800.00",
                "800.25", 1499956299040, "50250000.0", 30000, "400.5", "25125000.0", "0"
            ],
        ]

        monkeypatch.setattr(client, "_future_exchange", mock_exchange)

        klines = client.get_future_klines(
            symbol="BTCUSDT",
            interval="1h",
            limit=2,
        )

        assert len(klines) == 2
        assert klines[0].open_price == "62000.00"
        assert klines[0].close_price_float == 62250.00
        assert klines[0].volume_float == 1000.5
        assert klines[0].trade_count == 50000
        assert klines[1].high_price_float == 63000.00

        # 验证调用参数
        mock_exchange.fapiPublicGetKlines.assert_called_once_with({
            "symbol": "BTCUSDT",
            "interval": "1h",
            "limit": 2,
        })

    def test_get_future_klines_with_time_range_mock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试获取带时间范围的 K 线（mock 版本）。"""
        client = BinanceClient()

        mock_exchange = MagicMock()
        mock_exchange.fapiPublicGetKlines.return_value = []

        monkeypatch.setattr(client, "_future_exchange", mock_exchange)

        start_ts = 1499783499040
        end_ts = 1499869899040

        client.get_future_klines(
            symbol="BTCUSDT",
            interval="15m",
            limit=100,
            start_time=start_ts,
            end_time=end_ts,
        )

        mock_exchange.fapiPublicGetKlines.assert_called_once_with({
            "symbol": "BTCUSDT",
            "interval": "15m",
            "limit": 100,
            "startTime": start_ts,
            "endTime": end_ts,
        })

    def test_close_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试关闭会话。"""
        close_called = False

        def mock_close(self) -> None:  # noqa: ANN001
            nonlocal close_called
            close_called = True

        monkeypatch.setattr(requests.Session, "close", mock_close)

        client = BinanceClient()
        # 先初始化 ccxt 实例
        _ = client.future_exchange
        # mock ccxt 的 close 方法
        mock_ccxt_close = MagicMock()
        monkeypatch.setattr(client._future_exchange, "close", mock_ccxt_close)

        client.close()

        assert close_called is True
        assert mock_ccxt_close.call_count == 1


class TestBinanceClientIntegration:
    """集成测试（可选运行）。

    这些测试会真实调用外部 API，默认跳过。
    如需运行: pytest tests/test_binance_client.py -v --run-integration
    """

    @pytest.mark.integration
    def test_real_alpha_tokens_api(self) -> None:
        """真实调用币安阿尔法代币 API。"""
        with BinanceClient(timeout=30) as client:
            tokens = client.get_alpha_tokens()

            assert len(tokens) > 0
            assert all(t.symbol for t in tokens)
            assert all(t.name for t in tokens)

            # 检查至少有一个代币有市值数据
            has_market_cap = any(t.market_cap and t.market_cap > 0 for t in tokens)
            assert has_market_cap, "至少应该有一个代币有市值数据"

            print(f"\n✅ 获取到 {len(tokens)} 个阿尔法代币")

    @pytest.mark.integration
    def test_real_future_exchange_info(self) -> None:
        """真实调用币安合约交易所信息 API。"""
        with BinanceClient(timeout=30) as client:
            info = client.get_future_exchange_info()

            assert info.timezone == "UTC"
            assert info.server_time > 0
            assert len(info.symbols) > 0
            assert len(info.assets) > 0
            assert len(info.rate_limits) > 0

            # 验证 BTCUSDT 交易对数据
            btc = [s for s in info.symbols if s.symbol == "BTCUSDT"][0]
            assert btc.status == "TRADING"
            assert btc.contract_type == "PERPETUAL"
            assert btc.price_precision >= 0
            assert btc.quantity_precision >= 0

            print(f"\n✅ 交易所信息: {len(info.symbols)} 个交易对, {len(info.assets)} 个资产")

    @pytest.mark.integration
    def test_real_future_ticker_24hr(self) -> None:
        """真实调用币安合约 24 小时行情 API。"""
        with BinanceClient(timeout=30) as client:
            # 获取所有交易对行情
            all_tickers = client.get_future_ticker_24hr()
            assert len(all_tickers) > 0

            # 获取单个交易对行情
            btc_tickers = client.get_future_ticker_24hr(symbol="BTCUSDT")
            assert len(btc_tickers) == 1
            btc = btc_tickers[0]
            assert btc.symbol == "BTCUSDT"
            assert btc.last_price_float > 0
            assert btc.count > 0

            # 验证数值属性
            assert isinstance(btc.price_change_percent_float, float)
            assert isinstance(btc.volume_float, float)
            assert isinstance(btc.quote_volume_float, float)
            assert isinstance(btc.high_price_float, float)
            assert isinstance(btc.low_price_float, float)

            print(f"\n✅ 获取到 {len(all_tickers)} 个交易对的行情数据")
            print(f"   BTCUSDT 价格: {btc.last_price} USDT")
            print(f"   BTCUSDT 24h 涨跌: {btc.price_change_percent}%")
            print(f"   BTCUSDT 24h 成交量: {btc.volume} BTC")
            print(f"   BTCUSDT 24h 成交额: {btc.quote_volume} USDT")
            print(f"   BTCUSDT 24h 成交笔数: {btc.count:,}")

    @pytest.mark.integration
    def test_real_future_klines(self) -> None:
        """真实调用币安合约 K 线 API。"""
        with BinanceClient(timeout=30) as client:
            # 获取不同时间周期的 K 线
            klines_1h = client.get_future_klines(
                symbol="BTCUSDT",
                interval="1h",
                limit=10,
            )
            assert len(klines_1h) == 10
            
            klines_15m = client.get_future_klines(
                symbol="BTCUSDT",
                interval="15m",
                limit=5,
            )
            assert len(klines_15m) == 5

            # 验证 K 线数据
            kline = klines_1h[0]
            assert kline.open_time > 0
            assert kline.close_time > kline.open_time
            assert kline.high_price_float >= kline.low_price_float
            assert kline.volume_float >= 0
            assert kline.trade_count >= 0

            # 验证涨跌判断逻辑正常
            assert isinstance(kline.is_up, bool)
            assert isinstance(kline.is_down, bool)

            print(f"\n✅ K 线数据验证通过")
            print(f"   1小时 K 线: {len(klines_1h)} 根")
            print(f"   15分钟 K 线: {len(klines_15m)} 根")
            print(f"   BTC 最新价: {kline.close_price} USDT")
            print(f"   K线状态: {'📈 上涨' if kline.is_up else '📉 下跌'}")
