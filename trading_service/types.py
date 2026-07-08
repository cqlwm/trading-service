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
