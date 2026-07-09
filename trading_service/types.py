from __future__ import annotations

from enum import Enum


class TradeDirection(str, Enum):
    """交易方向。"""

    LONG = "long"
    SHORT = "short"


class OrderType(str, Enum):
    """订单类型。"""

    OPEN = "OPEN"  # 开仓
    ADD = "ADD"  # 加仓
    REDUCE = "REDUCE"  # 减仓
    CLOSE = "CLOSE"  # 平仓


class MarketDirection(str, Enum):
    """市场方向。"""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CrossSignalType(str, Enum):
    """200 均线穿越信号类型。"""

    GOLDEN = "golden"  # 金叉向上：收盘价从下向上穿越 SMA200
    DEAD = "dead"  # 死叉向下：收盘价从上向下穿越 SMA200
    NEAR = "near"  # 靠近均线：无穿越但价格在均线附近
