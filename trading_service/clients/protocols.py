"""市场数据客户端协议（Protocol）。

定义 AlphaTokenSource / TechnicalAnalysisFilter 等消费者所需的客户端能力子集，
降低与具体 BinanceClient 的耦合，便于单元测试注入内存实现（duck typing）。

BinanceClient 在结构上满足这些协议，无需显式继承（Protocol 是结构化类型）。
按消费者实际需要拆分协议：
- AlphaTokenSource 只需 AlphaUniverseClient（Alpha 代币 + 交易所信息）
- TechnicalAnalysisFilter 只需 KlineClient（K 线拉取）
- MarketDataClient 是两者的超集，供需要全部能力的消费者使用。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from trading_service.clients.binance_client import (
    BinanceAlphaToken,
    BinanceFutureExchangeInfo,
    BinanceFutureKline,
)


@runtime_checkable
class KlineClient(Protocol):
    """K 线客户端协议：仅需拉取 K 线（TechnicalAnalysisFilter / BullishKlineFilter 依赖）。"""

    def get_future_klines(
        self, symbol: str, interval: str, limit: int = 500,
    ) -> list[BinanceFutureKline]:
        """获取合约 K 线数据。"""
        ...


@runtime_checkable
class AlphaUniverseClient(Protocol):
    """Alpha 宇宙客户端协议：Alpha 代币列表 + 交易所信息（AlphaTokenSource 依赖）。"""

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        """获取 Alpha 代币列表。"""
        ...

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        """获取合约交易所信息（含可交易交易对）。"""
        ...


@runtime_checkable
class MarketDataClient(KlineClient, AlphaUniverseClient, Protocol):
    """市场数据客户端协议：K 线 + Alpha 代币 + 交易所信息的完整能力集。

    继承 KlineClient 和 AlphaUniverseClient，供需要全部能力的消费者使用。
    """

