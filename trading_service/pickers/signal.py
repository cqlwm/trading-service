"""技术信号判定工具：从 SymbolInfo 提炼可关注信号。

与 TechnicalAnalysisFilter 的「纯增强不丢弃」职责分离：
- filter 只回填技术字段，保留所有代币；
- 本模块判定单个 SymbolInfo 是否值得关注，供展示层/策略层按需过滤。
"""
from __future__ import annotations

from trading_service.pickers.base import SymbolInfo
from trading_service.pickers.symbol_picker import PERPETUAL_DELIVERY_SENTINEL
from trading_service.types import CrossSignalType

# 值得关注的穿越信号（死叉 DEAD 属于消极信号，不在此列）
_NOTABLE_CROSS_SIGNALS = frozenset({CrossSignalType.GOLDEN, CrossSignalType.NEAR})


def is_notable_signal(info: SymbolInfo) -> bool:
    """是否为值得关注的技术信号：金叉 / 靠近均线 / 底部横盘。

    死叉(DEAD)与无信号(None)返回 False。
    底部横盘优先：即便穿越信号为死叉，只要横盘即为关注信号。
    """
    if info.is_sideways_bottom:
        return True
    return info.cross_signal in _NOTABLE_CROSS_SIGNALS


def is_delisting_soon(info: SymbolInfo) -> bool:
    """是否即将下架：delivery_date 偏离永续哨兵值即为下架流程相关。

    - 哨兵值（4133404800000）= 正常永续，永不到期 -> False
    - 具体时点 = Binance 已设定下架时点（提前约 15 天预警） -> True
    - None = 未知（数据源未回填） -> False（不报警）

    注意：即便下架时点已过（status 可能已转 SETTLING/CLOSE），只要 delivery_date
    偏离哨兵值即返回 True，因为下架流程已启动。
    """
    if info.delivery_date is None:
        return False
    return info.delivery_date != PERPETUAL_DELIVERY_SENTINEL
