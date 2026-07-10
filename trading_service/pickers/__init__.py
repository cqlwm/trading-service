from trading_service.pickers.base import (
    ISymbolPicker,
    StaticListSymbolPicker,
    SymbolInfo,
)
from trading_service.pickers.pipeline import (
    ISymbolFilter,
    ISymbolSource,
    SelectionPipeline,
)
from trading_service.pickers.backtest import (
    BacktestResult,
    BacktestTrade,
    PortfolioConfig,
    SignalEntry,
    scan_tp,
    simulate_portfolio,
    simulate_trade,
    summarize,
)
from trading_service.pickers.signal import is_delisting_soon, is_notable_signal
from trading_service.pickers.short_signal_filter import ShortSignalFilter
from trading_service.pickers.symbol_picker import (
    PERPETUAL_DELIVERY_SENTINEL,
    AlphaTokenSource,
)
from trading_service.pickers.technical_analyzer import (
    CrossSignal,
    ITechnicalAnalyzer,
    TechnicalAnalyzer,
)
from trading_service.pickers.technical_filter import TechnicalAnalysisFilter
from trading_service.pickers.top_gainers_source import TopGainersSource

__all__ = [
    # 核心契约（策略层依赖）
    "ISymbolPicker",
    "SymbolInfo",
    "StaticListSymbolPicker",
    # 管道抽象（组装层依赖）
    "ISymbolSource",
    "ISymbolFilter",
    "SelectionPipeline",
    # 数据源实现
    "AlphaTokenSource",
    "TopGainersSource",
    # 技术分析
    "ITechnicalAnalyzer",
    "TechnicalAnalyzer",
    "TechnicalAnalysisFilter",
    "CrossSignal",
    # 过滤器实现
    "ShortSignalFilter",
    # 技术信号判定（展示层/策略层按需过滤）
    "is_notable_signal",
    "is_delisting_soon",
    # 合约生命周期
    "PERPETUAL_DELIVERY_SENTINEL",
    # 回测
    "BacktestTrade",
    "BacktestResult",
    "SignalEntry",
    "PortfolioConfig",
    "simulate_trade",
    "simulate_portfolio",
    "summarize",
    "scan_tp",
]
