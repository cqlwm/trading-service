"""BinanceClient 测试。"""
from __future__ import annotations

import pytest
import requests

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceAlphaTokenListResponse,
    BinanceClient,
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

    def test_close_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试关闭会话。"""
        close_called = False

        def mock_close(self) -> None:
            nonlocal close_called
            close_called = True

        monkeypatch.setattr(requests.Session, "close", mock_close)

        client = BinanceClient()
        client.close()

        assert close_called is True




class TestBinanceClientIntegration:
    """集成测试（可选运行）。

    这些测试会真实调用外部 API，默认跳过。
    如需运行: pytest tests/test_binance_client.py -m integration
    """

    @pytest.mark.integration
    def test_real_api_call(self) -> None:
        """真实调用币安 API 测试。"""
        with BinanceClient(timeout=30) as client:
            tokens = client.get_alpha_tokens()

            assert len(tokens) > 0
            assert all(t.symbol for t in tokens)
            assert all(t.name for t in tokens)

            # 检查至少有一个代币有市值数据
            has_market_cap = any(t.market_cap and t.market_cap > 0 for t in tokens)
            assert has_market_cap, "至少应该有一个代币有市值数据"

            print(f"\n✅ 真实 API 测试通过，获取到 {len(tokens)} 个代币")
