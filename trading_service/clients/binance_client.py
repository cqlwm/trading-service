from __future__ import annotations

import logging
from typing import Any

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
    def parse_float_fields(cls, v: Any) -> float | None:
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
    def parse_int_fields(cls, v: Any) -> int | None:
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


class BinanceClient:
    """币安 API 客户端。

    封装币安 BAPI 接口，用于获取阿尔法代币列表等数据。
    """

    BASE_URL = "https://www.binance.com/bapi"

    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def close(self) -> None:
        """关闭会话。"""
        self.session.close()

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
