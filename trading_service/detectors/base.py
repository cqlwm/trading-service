"""信号检测器基类。

信号检测器是策略的组件，接收策略选好的候选币列表进行信号检测。
检测器不负责选币，由策略通过 symbol_picker 选币后传入。
产出的信号落盘到 trading_signals 表。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trading_service.pickers import SymbolInfo
from trading_service.repository import TradingRepository


@dataclass
class SignalResult:
    """信号检测器产出的单条信号（内存对象，由策略落盘为 SignalRecord）。"""

    symbol: str
    signal_type: str           # 如 "golden_cross", "consecutive_rise", "volume_surge"
    direction: str             # "bullish" | "bearish" | "neutral"
    severity: int = 0          # 0-5
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class SignalDetector(ABC):
    """信号检测器 -- 策略组件，接收候选币列表进行信号检测。

    检测器不负责选币，由策略通过 symbol_picker 选币后传入。
    产出的信号落盘到 trading_signals 表。
    信号可被策略消费（驱动交易），也可不被消费（仅用于内容生成）。
    """

    name: str = ""  # 检测器标识

    def __init__(self, repo: TradingRepository) -> None:
        self._repo = repo

    @abstractmethod
    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币列表进行信号检测，产出信号列表。"""

    def get_status(self) -> dict[str, Any]:
        """获取检测器状态。"""
        return {"name": self.name}
