from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from trading_service.config import settings
from trading_service.exchange import MockExchange
from trading_service.pickers import (
    AlphaTokenSource,
    BullishKlineFilter,
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
# 技术信号检测器（作为微市值策略的组件，接收策略选好的候选币进行检测）
_technical_signal_detector = TechnicalSignalDetector(repo=_trading_store, client=_micro_cap_client)
_micro_cap_strategy = MicroCapStrategy(
    exchange=_exchange,
    config=MicroCapConfig(),
    symbol_picker=SelectionPipeline(
        source=AlphaTokenSource(client=_micro_cap_client),
        filters=[
            BullishKlineFilter(client=_micro_cap_client, interval="1d", limit=5),
            TechnicalAnalysisFilter(
                analyzer=TechnicalAnalyzer(),
                client=_micro_cap_client,
                kline_interval="4h",
            ),
        ],
    ),
    signal_detectors=[_technical_signal_detector],
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
# 内容型策略：涨幅榜选币 -> 连续涨跌K线检测 -> 选 1 条生成贴文
from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
from trading_service.strategies.content_scan import ContentScanConfig, ContentScanStrategy

_consecutive_candle_detector = ConsecutiveCandleDetector(
    repo=_trading_store, client=_micro_cap_client, interval="1d", min_streak=3,
)
_content_scan_strategy = ContentScanStrategy(
    exchange=_exchange,
    config=ContentScanConfig(),
    symbol_picker=SelectionPipeline(
        source=TopGainersSource(client=_micro_cap_client, top_n=20),
    ),
    signal_detectors=[_consecutive_candle_detector],
)

# 贴文生成器（LLM 生成交易动态贴文，api_key 为空时自动跳过）
from trading_service.content import PostGenerator, create_openai_client

_post_generator: PostGenerator | None = None
if settings.posts_enabled:
    _llm_result = create_openai_client(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    if _llm_result is not None:
        _post_generator = PostGenerator(
            repo=_trading_store,
            posts_dir=settings.posts_dir,
            llm_client=_llm_result[0],
            llm_model=_llm_result[1],
        )

# 统一策略调度器（管理所有策略的定时执行，信号检测器作为策略组件由策略内部调用）
_strategy_scheduler = StrategyScheduler(
    repo=_trading_store,
    strategies=[_martingale_strategy, _micro_cap_strategy, _martingale_short_strategy, _content_scan_strategy],
    post_generator=_post_generator,
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
