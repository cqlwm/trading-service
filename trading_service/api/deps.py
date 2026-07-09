from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from trading_service.config import settings
from trading_service.exchange import MockExchange
from trading_service.pickers import (
    AlphaTokenSource,
    SelectionPipeline,
    StaticListSymbolPicker,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
)
from trading_service.repository import SqlalchemyTradingStore
from trading_service.strategies.martingale import MartingaleConfig, MartingaleStrategy
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
from trading_service.clients import BinanceClient
from trading_service.utils.symbol import Symbol

# 全局单例
_trading_store = SqlalchemyTradingStore(settings.db_path)
_exchange = MockExchange(db=_trading_store)
_martingale_strategy = MartingaleStrategy(
    exchange=_exchange,
    config=MartingaleConfig(),
    # 统一使用 binance 原生格式（BTCUSDT），与 DB 存储、fetch_prices key 对齐
    symbol_picker=StaticListSymbolPicker(
        [Symbol("BTC", "USDT").binance(), Symbol("ETH", "USDT").binance()]
    ),
)
# 微市值：选币（AlphaTokenSource）-> 技术分析增强（TechnicalAnalysisFilter）-> 策略
_micro_cap_client = BinanceClient(timeout=30)
_micro_cap_strategy = MicroCapStrategy(
    exchange=_exchange,
    config=MicroCapConfig(),
    symbol_picker=SelectionPipeline(
        source=AlphaTokenSource(client=_micro_cap_client),
        filters=[
            TechnicalAnalysisFilter(
                analyzer=TechnicalAnalyzer(),
                client=_micro_cap_client,
                kline_interval="4h",
            ),
        ],
    ),
)


async def get_exchange() -> MockExchange:
    """获取 MockExchange 实例。"""
    return _exchange


async def get_martingale_strategy() -> MartingaleStrategy:
    """获取马丁策略实例。"""
    return _martingale_strategy


async def get_micro_cap_strategy() -> MicroCapStrategy:
    """获取微市值策略实例。"""
    return _micro_cap_strategy


ExchangeDep = Annotated[MockExchange, Depends(get_exchange)]
MartingaleDep = Annotated[MartingaleStrategy, Depends(get_martingale_strategy)]
MicroCapDep = Annotated[MicroCapStrategy, Depends(get_micro_cap_strategy)]
