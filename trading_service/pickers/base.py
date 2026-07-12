"""选币核心契约：SymbolInfo、ISymbolPicker、StaticListSymbolPicker。

放在独立模块以打破循环依赖：
- pipeline.py 导入 ISymbolPicker / SymbolInfo
- symbol_picker.py 的 AlphaTokenSource 导入 pipeline.ISymbolSource
两者都依赖本模块，本模块不依赖任何 picker 子模块。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from trading_service.types import CrossSignalType


@dataclass
class SymbolInfo:
    """代币信息。

    同时承载基础字段（所有数据源通用）与技术分析字段（由 TechnicalAnalysisFilter 回填）。
    数据源（如 AlphaTokenSource）只填充基础字段，技术字段保持默认值。

    klines 字段承载 K 线数据和所有技术指标（DataFrame），一次拉取处处复用。
    加新指标只需在 DataFrame 上追加列，不需要修改本 dataclass。
    """

    # === 基础字段（所有数据源通用）===
    symbol: str  # 交易对符号（如 BTCUSDT）
    price: float = 0.0  # 当前价格
    volume_24h: float = 0.0  # 24小时成交量
    market_cap: float = 0.0  # 市值（USDT）
    price_change_pct_24h: float = 0.0  # 24小时涨跌幅

    # === Alpha 选币扩展字段 ===
    base_asset: str = ""  # 基础资产（如 BTC）
    yesterday_change_percent: float = 0.0  # 昨日涨跌幅（%）
    yesterday_open: float = 0.0  # 昨日开盘价
    yesterday_close: float = 0.0  # 昨日收盘价

    # === 技术分析字段（由 TechnicalAnalysisFilter 回填，从 klines 派生，过渡保留）===
    sma_200: float | None = None  # 200均线价格
    price_vs_sma200_percent: float | None = None  # 价格相对均线的距离%
    cross_signal: CrossSignalType | None = None  # 穿越信号: GOLDEN/DEAD/NEAR/None
    cross_ago: int | None = None  # 多少根K线之前穿越的
    is_sideways_bottom: bool = False  # 是否底部横盘
    volatility_10: float | None = None  # 最近10根K线波动率%

    # === K 线 + 指标 DataFrame（由 TechnicalAnalysisFilter 构建）===
    # 列：datetime, open, high, low, close, volume, sma_200, cross_signal, ...
    # 加新指标只需追加列，不改 SymbolInfo。检测器和策略复用此 DataFrame。
    klines: pd.DataFrame | None = None

    # === 合约生命周期字段（由 AlphaTokenSource 从 exchangeInfo 回填）===
    delivery_date: int | None = None  # 交割/下架日期(ms)；永续正常=哨兵值，即将下架=具体时点


class ISymbolPicker(ABC):
    """选币器接口（策略层契约）。

    策略只依赖此接口；具体实现可以是 StaticListSymbolPicker、
    或组合 source+filters 的 SelectionPipeline。
    """

    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:
        """筛选符合条件的币种。"""
        ...


class StaticListSymbolPicker(ISymbolPicker):
    """静态列表币种选择器。

    兼容策略框架的 async 接口。
    """

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        """返回静态的币种列表。"""
        return [
            SymbolInfo(
                symbol=s,
                price=0.0,
                volume_24h=0.0,
                market_cap=0.0,
                price_change_pct_24h=0.0,
            )
            for s in self.symbols
        ]
