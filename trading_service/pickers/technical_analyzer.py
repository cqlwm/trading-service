from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.clients import BinanceFutureKline


@dataclass
class CrossSignal:
    """均线穿越信号。"""

    symbol: str
    cross_type: str  # "golden": 金叉向上, "dead": 死叉向下, "near": 靠近均线
    cross_ago: int  # 多少根K线之前发生的穿越（0是刚发生）
    current_price: float
    sma_200: float
    distance_percent: float  # 价格与均线的距离百分比
    volatility_10: float  # 最近10根K线的波动率
    is_sideways: bool  # 是否处于底部横盘


class ITechnicalAnalyzer(ABC):
    """技术分析器接口。

    通过依赖注入提供给 SymbolPicker，便于单元测试时替换为 mock 实现。
    """

    @abstractmethod
    def detect_200sma_signal(
        self,
        klines: list[BinanceFutureKline],
        symbol: str,
        check_last_n: int = 10,
        near_threshold: float = 5.0,
        sideways_threshold: float = 20.0,
    ) -> CrossSignal | None:
        """检测200均线穿越信号。"""
        ...


class TechnicalAnalyzer(ITechnicalAnalyzer):
    """技术分析工具类。

    提供 SMA 计算、200均线穿越信号检测、底部横盘判定等能力。
    所有计算方法无状态，可安全共享单例。
    """

    @staticmethod
    def calculate_sma(klines: list[BinanceFutureKline], period: int) -> list[float | None]:
        """计算简单移动平均线(SMA)。

        返回与 klines 等长的列表，前 period-1 个为 None（数据不足）。
        """
        closes = [k.close_price_float for k in klines]
        sma_values: list[float | None] = [None] * len(klines)

        for i in range(period - 1, len(closes)):
            period_sum = sum(closes[i - period + 1:i + 1])
            sma_values[i] = period_sum / period

        return sma_values

    def detect_200sma_signal(
        self,
        klines: list[BinanceFutureKline],
        symbol: str,
        check_last_n: int = 10,
        near_threshold: float = 5.0,
        sideways_threshold: float = 20.0,
    ) -> CrossSignal | None:
        """检测200均线穿越信号。

        优先级：金叉/死叉穿越 > 靠近均线。无穿越且远离均线时返回 None。
        """
        if len(klines) < 201:
            return None

        sma_values = TechnicalAnalyzer.calculate_sma(klines, 200)

        # 找最近的穿越点
        last_cross_idx = -1
        last_cross_type = ""

        for i in range(len(klines) - check_last_n, len(klines)):
            prev_sma = sma_values[i - 1]
            curr_sma = sma_values[i]
            if prev_sma is None or curr_sma is None:
                continue

            prev_close = klines[i - 1].close_price_float
            curr_close = klines[i].close_price_float

            # 金叉：收盘价从下向上穿越SMA200
            if prev_close <= prev_sma and curr_close > curr_sma:
                last_cross_idx = i
                last_cross_type = "golden"

            # 死叉：收盘价从上向下穿越SMA200
            elif prev_close >= prev_sma and curr_close < curr_sma:
                last_cross_idx = i
                last_cross_type = "dead"

        # 计算当前价格与均线的距离
        last_sma = sma_values[-1]
        if last_sma is None:
            return None

        last_price = klines[-1].close_price_float
        distance_percent = ((last_price - last_sma) / last_sma) * 100

        # 计算最近10根K线波动率（复用 is_bottom_sideways 的波动率逻辑）
        volatility = self._calculate_volatility(klines[-10:])
        is_sideways = self._is_sideways(
            volatility, last_price, last_sma, distance_percent, sideways_threshold
        )

        # 优先返回穿越信号
        if last_cross_idx > 0:
            cross_ago = len(klines) - 1 - last_cross_idx
            return CrossSignal(
                symbol=symbol,
                cross_type=last_cross_type,
                cross_ago=cross_ago,
                current_price=last_price,
                sma_200=last_sma,
                distance_percent=distance_percent,
                volatility_10=volatility,
                is_sideways=is_sideways,
            )

        # 无穿越但靠近均线
        if abs(distance_percent) <= near_threshold:
            return CrossSignal(
                symbol=symbol,
                cross_type="near",
                cross_ago=-1,
                current_price=last_price,
                sma_200=last_sma,
                distance_percent=distance_percent,
                volatility_10=volatility,
                is_sideways=is_sideways,
            )

        return None

    @staticmethod
    def is_bottom_sideways(
        klines: list[BinanceFutureKline],
        period: int = 30,
        volatility_threshold: float = 25.0,
    ) -> bool:
        """判断是否处于底部横盘（波动率低于阈值）。"""
        if len(klines) < period:
            return False

        recent_klines = klines[-period:]
        volatility = TechnicalAnalyzer._calculate_volatility(recent_klines)
        return volatility <= volatility_threshold

    @staticmethod
    def _calculate_volatility(klines: list[BinanceFutureKline]) -> float:
        """计算给定K线的波动率 = (high-low)/low*100，数据不足或 low=0 时返回 999.0。"""
        if len(klines) < 10:
            return 999.0

        high = max(k.high_price_float for k in klines)
        low = min(k.low_price_float for k in klines)
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
        return (
            volatility <= sideways_threshold
            and last_price > last_sma
            and abs(distance_percent) <= 15
        )
