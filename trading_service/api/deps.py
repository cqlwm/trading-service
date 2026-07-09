from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from trading_service.config import settings
from trading_service.exchange import MockExchange
from trading_service.pickers import SimpleAlphaSymbolPicker, StaticListSymbolPicker
from trading_service.repository import SqlalchemyTradingStore
from trading_service.strategies.martingale import MartingaleConfig, MartingaleStrategy
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
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
_micro_cap_strategy = MicroCapStrategy(
    exchange=_exchange,
    config=MicroCapConfig(),
    # 微市值选币：市值<5000万 + 昨日上涨 + 200均线技术分析
    symbol_picker=SimpleAlphaSymbolPicker(enable_technical_filter=True),
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
