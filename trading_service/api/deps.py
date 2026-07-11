from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from trading_service.config import settings
from trading_service.exchange import MockExchange
from trading_service.pickers import (
    AlphaTokenSource,
    SelectionPipeline,
    ShortSignalFilter,
    StaticListSymbolPicker,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
    TopGainersSource,
)
from trading_service.repository import SqlalchemyTradingStore
from trading_service.scheduler import StrategyScheduler
from trading_service.strategies.martingale import MartingaleConfig, MartingaleStrategy
from trading_service.strategies.martingale_short import MartingaleShortStrategy
from trading_service.strategies.micro_cap import MicroCapConfig, MicroCapStrategy
from trading_service.clients import BinanceClient
from trading_service.detectors.technical import TechnicalSignalDetector
from trading_service.types import TradeDirection
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
# 马丁做空：涨幅榜选币 -> 技术分析增强 -> 做空信号过滤 -> 做空马丁策略
_martingale_short_strategy = MartingaleShortStrategy(
    exchange=_exchange,
    config=MartingaleConfig(
        direction=TradeDirection.SHORT,
        max_positions=5,
        base_order_size=50.0,
        safety_order_count=3,
        take_profit_pct=2.0,
        stop_loss_pct=15.0,
    ),
    symbol_picker=SelectionPipeline(
        source=TopGainersSource(client=_micro_cap_client, top_n=20),
        filters=[
            TechnicalAnalysisFilter(
                analyzer=TechnicalAnalyzer(),
                client=_micro_cap_client,
                kline_interval="4h",
            ),
            ShortSignalFilter(overbought_threshold=15.0),
        ],
    ),
)
# 信号检测器（与策略平行，由调度器定时调度）
_technical_signal_detector = TechnicalSignalDetector(repo=_trading_store, client=_micro_cap_client)

# 统一策略调度器（管理所有策略和检测器的定时执行）
_strategy_scheduler = StrategyScheduler(
    repo=_trading_store,
    strategies=[_martingale_strategy, _micro_cap_strategy, _martingale_short_strategy],
    detectors=[_technical_signal_detector],
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


async def get_martingale_short_strategy() -> MartingaleShortStrategy:
    """获取马丁做空策略实例。"""
    return _martingale_short_strategy


def get_strategy_scheduler() -> StrategyScheduler:
    """获取策略调度器实例。"""
    return _strategy_scheduler


ExchangeDep = Annotated[MockExchange, Depends(get_exchange)]
MartingaleDep = Annotated[MartingaleStrategy, Depends(get_martingale_strategy)]
MicroCapDep = Annotated[MicroCapStrategy, Depends(get_micro_cap_strategy)]
MartingaleShortDep = Annotated[MartingaleShortStrategy, Depends(get_martingale_short_strategy)]
SchedulerDep = Annotated[StrategyScheduler, Depends(get_strategy_scheduler)]
