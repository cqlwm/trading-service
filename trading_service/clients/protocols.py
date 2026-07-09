"""市场数据客户端协议（Protocol）。

定义 AlphaTokenSource / TechnicalAnalysisFilter 等消费者所需的客户端能力子集，
降低与具体 BinanceClient 的耦合，便于单元测试注入内存实现（duck typing）。

BinanceClient 在结构上满足这些协议，无需显式继承（Protocol 是结构化类型）。
按消费者实际需要拆分协议：TechnicalAnalysisFilter 只需 KlineClient，
AlphaTokenSource 需要更全的 MarketDataClient（KlineClient 的超集）。
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
    """K 线客户端协议：仅需拉取 K 线（TechnicalAnalysisFilter 依赖）。"""

    def get_future_klines(
        self, symbol: str, interval: str, limit: int = 500,
    ) -> list[BinanceFutureKline]:
        """获取合约 K 线数据。"""
        ...


@runtime_checkable
class MarketDataClient(KlineClient, Protocol):
    """市场数据客户端协议：选币所需的完整能力集（AlphaTokenSource 依赖）。

    继承 KlineClient，额外要求 Alpha 代币列表与交易所信息。
    """

    def get_alpha_tokens(self) -> list[BinanceAlphaToken]:
        """获取 Alpha 代币列表。"""
        ...

    def get_future_exchange_info(self) -> BinanceFutureExchangeInfo:
        """获取合约交易所信息（含可交易交易对）。"""
        ...

