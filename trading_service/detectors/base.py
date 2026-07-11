"""信号检测器基类。

信号检测器与策略平行，由调度器定时调度。
产出信号落盘到 trading_signals 表。
信号可被策略消费（驱动交易），也可不被消费（仅用于内容生成）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from trading_service.repository import TradingRepository


@dataclass
class SignalResult:
    """信号检测器产出的单条信号（内存对象，由调度器转换为 SignalRecord 落盘）。"""

    symbol: str
    signal_type: str           # 如 "golden_cross", "consecutive_rise", "volume_surge"
    direction: str             # "bullish" | "bearish" | "neutral"
    severity: int = 0          # 0-5
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


class SignalDetector(ABC):
    """信号检测器基类 -- 与策略平行，由调度器定时调度。

    产出信号落盘到 trading_signals 表。
    信号可被策略消费（驱动交易），也可不被消费（仅用于内容生成）。
    """

    name: str = ""   # 检测器标识（用于调度注册）
    cron: str = ""   # cron 表达式（空=不参与定时调度）

    def __init__(self, repo: TradingRepository) -> None:
        self._repo = repo

    @abstractmethod
    async def detect(self) -> list[SignalResult]:
        """扫描市场，产出信号列表。"""

    def get_status(self) -> dict[str, Any]:
        """获取检测器状态。"""
        return {"name": self.name, "cron": self.cron}
