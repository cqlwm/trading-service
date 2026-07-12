"""技术分析器 -- 基于 DataFrame 的信号判定。

接收 pd.DataFrame（含 OHLCV 列），判定金叉/死叉/横盘等信号。
指标计算使用 TA-Lib，本类只负责复合信号判定逻辑。

BinanceFutureKline 是网络层 DTO，不穿透到本层。
K 线数据在 TechnicalAnalysisFilter 中从 list[BinanceFutureKline] 转为 DataFrame 后传入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd
import talib

from trading_service.types import CrossSignalType


@dataclass
class CrossSignal:
    """均线穿越信号。"""

    symbol: str
    cross_type: CrossSignalType  # 金叉向上 / 死叉向下 / 靠近均线
    cross_ago: int  # 多少根K线之前发生的穿越（0是刚发生）
    current_price: float
    sma_200: float
    distance_percent: float  # 价格与均线的距离百分比
    volatility_10: float  # 最近10根K线的波动率
    is_sideways: bool  # 是否处于底部横盘


class ITechnicalAnalyzer(ABC):
    """技术分析器接口。

    通过依赖注入提供给 TechnicalAnalysisFilter，便于单元测试时替换为 mock 实现。
    """

    @abstractmethod
    def detect_200sma_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        check_last_n: int = 10,
        near_threshold: float = 5.0,
        sideways_threshold: float = 20.0,
    ) -> CrossSignal | None:
        """检测200均线穿越信号。

        Args:
            df: 含 open/high/low/close/volume 列的 DataFrame
            symbol: 交易对符号
            check_last_n: 扫描最近 N 根 K 线寻找穿越
            near_threshold: 靠近均线的距离阈值（%）
            sideways_threshold: 横盘判定的波动率阈值（%）
        """
        ...


class TechnicalAnalyzer(ITechnicalAnalyzer):
    """技术分析工具类。

    基于 DataFrame 进行信号判定。指标计算使用 TA-Lib，本类只负责复合判定逻辑。
    所有计算方法无状态，可安全共享单例。
    """

    def detect_200sma_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        check_last_n: int = 10,
        near_threshold: float = 5.0,
        sideways_threshold: float = 20.0,
    ) -> CrossSignal | None:
        """检测200均线穿越信号。

        优先级：金叉/死叉穿越 > 靠近均线。无穿越且远离均线时返回 None。
        """
        if len(df) < 201:
            return None

        closes = df["close"].to_numpy(dtype=float)
        sma_values = talib.SMA(closes, timeperiod=200)

        # 找最近的穿越点
        last_cross_idx = -1
        last_cross_type: CrossSignalType | None = None

        start = max(1, len(df) - check_last_n)
        for i in range(start, len(df)):
            prev_sma = sma_values[i - 1]
            curr_sma = sma_values[i]
            if prev_sma is None or curr_sma is None:
                continue
            if not (prev_sma == prev_sma and curr_sma == curr_sma):  # NaN check
                continue

            prev_close = closes[i - 1]
            curr_close = closes[i]

            # 金叉：收盘价从下向上穿越SMA200
            if prev_close <= prev_sma and curr_close > curr_sma:
                last_cross_idx = i
                last_cross_type = CrossSignalType.GOLDEN

            # 死叉：收盘价从上向下穿越SMA200
            elif prev_close >= prev_sma and curr_close < curr_sma:
                last_cross_idx = i
                last_cross_type = CrossSignalType.DEAD

        # 计算当前价格与均线的距离
        last_sma = sma_values[-1]
        if last_sma is None or last_sma != last_sma:  # NaN check
            return None

        last_price = float(closes[-1])
        distance_percent = float(((last_price - last_sma) / last_sma) * 100)

        # 计算最近10根K线波动率
        volatility = self._calculate_volatility(df.tail(10))
        is_sideways = self._is_sideways(
            volatility, last_price, float(last_sma), distance_percent, sideways_threshold
        )

        # 优先返回穿越信号
        if last_cross_idx > 0 and last_cross_type is not None:
            cross_ago = len(df) - 1 - last_cross_idx
            return CrossSignal(
                symbol=symbol,
                cross_type=last_cross_type,
                cross_ago=cross_ago,
                current_price=last_price,
                sma_200=float(last_sma),
                distance_percent=distance_percent,
                volatility_10=volatility,
                is_sideways=is_sideways,
            )

        # 无穿越但靠近均线
        if abs(distance_percent) <= near_threshold:
            return CrossSignal(
                symbol=symbol,
                cross_type=CrossSignalType.NEAR,
                cross_ago=-1,
                current_price=last_price,
                sma_200=float(last_sma),
                distance_percent=distance_percent,
                volatility_10=volatility,
                is_sideways=is_sideways,
            )

        return None

    @staticmethod
    def _calculate_volatility(df: pd.DataFrame) -> float:
        """计算给定K线的波动率 = (high-low)/low*100，数据不足或 low=0 时返回 999.0。"""
        if len(df) < 10:
            return 999.0

        high = float(df["high"].max())
        low = float(df["low"].min())
        if low <= 0:
            return 999.0

        return ((high - low) / low) * 100

    @staticmethod
    def _is_sideways(
        volatility: float,
        last_price: float,
        last_sma: float,
        distance_percent: float,
        sideways_threshold: float,
    ) -> bool:
        """综合判定横盘状态：低波动 + 价格在均线上方 + 距离适中。"""
        return bool(
            volatility <= sideways_threshold
            and last_price > last_sma
            and abs(distance_percent) <= 15
        )
