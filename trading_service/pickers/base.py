"""选币核心契约：SymbolInfo、ISymbolPicker、StaticListSymbolPicker。

放在独立模块以打破循环依赖：
- pipeline.py 导入 ISymbolPicker / SymbolInfo
- symbol_picker.py 的 AlphaTokenSource 导入 pipeline.ISymbolSource
两者都依赖本模块，本模块不依赖任何 picker 子模块。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SymbolInfo:
    """代币信息。

    基础字段由数据源（如 AlphaTokenSource）填充。
    所有技术指标统一由 klines DataFrame 承载，由各 filter 按需拉取并构建后处处复用，
    不在 dataclass 上保留冗余快照字段。
    """

    # === 基础字段（所有数据源通用）===
    symbol: str  # 交易对符号（如 BTCUSDT）
    price: float = 0.0  # 当前价格
    volume_24h: float = 0.0  # 24小时成交量
    price_change_pct_24h: float = 0.0  # 24小时涨跌幅

    market_cap: float = 0.0  # 市值（USDT）

    # === Alpha 选币扩展字段 ===
    base_asset: str = ""  # 基础资产（如 BTC）

    # === K 线 + 指标 DataFrame（多时间框架，按 interval 字符串索引）===
    # key 为 interval（如 "4h"、"1d"），value 为含 OHLCV + 指标列的 DataFrame。
    # 由各 filter 按需拉取并构建，检测器和策略复用，不重新拉取。
    # 加新指标只需追加列，加新时间框架只需追加 key，不改 SymbolInfo。
    klines: dict[str, pd.DataFrame] = field(default_factory=dict)

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
