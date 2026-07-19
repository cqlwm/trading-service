from __future__ import annotations

import uuid
from typing import Any

from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.repository import SignalRecord
from trading_service.detectors.base import SignalDetector


@dataclass
class StrategyAction:
    """策略执行动作记录，用于 API 响应反馈。"""

    type: str  # "open" | "add" | "close" | "skip"
    symbol: str
    reason: str = ""


@dataclass
class StrategyConfig:
    """策略配置基类。"""


class Strategy(ABC):
    """策略基类。"""

    # 策略标识，用于调度注册和 API 路径（子类必须覆盖）
    name: str = ""
    # cron 表达式（7 字段：秒 分 时 日 月 周 年），空=不参与定时调度
    # 示例："*/30 * * * * *" = 每30秒，"0 * * * * *" = 每分钟
    cron: str = ""

    def __init__(
        self,
        exchange: MockExchange,
        config: StrategyConfig,
        symbol_picker: ISymbolPicker,
        signal_detectors: list[SignalDetector] | None = None,
    ) -> None:
        self.exchange = exchange
        self.config = config
        self.symbol_picker = symbol_picker
        self.signal_detectors = signal_detectors or []

    @abstractmethod
    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行策略，返回执行的动作列表。

        execution_id 用于将动作记录关联到调度轮次（手动操作为空）。
        """

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""

    def get_recent_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        limit: int = 10,
    ) -> list[SignalRecord]:
        """拉取最近的信号（策略主动消费）。

        信号是市场观察，不是命令。看到同一个信号多次不应导致重复操作，
        策略自身的持仓检查（tag 隔离 + status 过滤）天然防止重复交易。
        """
        return self.exchange.db.list_signals(
            symbol=symbol, signal_type=signal_type, limit=limit,
        )

    async def run_detectors(
        self, candidates: list[SymbolInfo]
    ) -> list[SignalRecord]:
        """运行所有信号检测器，将产出的信号落盘并返回。

        检测器接收策略选好的候选币列表，产出信号落盘到 trading_signals 表。
        返回落盘的 SignalRecord 列表，策略可选择消费这些信号做决策。
        """
        if not self.signal_detectors:
            return []
        # 候选币市值快照：落盘信号时携带，供开仓环节取出存入 Position（开仓时定格）
        cap_by_symbol = {info.symbol: info.market_cap for info in candidates}
        saved_signals: list[SignalRecord] = []
        for detector in self.signal_detectors:
            results = await detector.detect(candidates)
            for result in results:
                metadata = dict(result.metadata)
                if result.symbol in cap_by_symbol:
                    metadata["market_cap"] = cap_by_symbol[result.symbol]
                signal = SignalRecord(
                    id=uuid.uuid4().hex[:12],
                    symbol=result.symbol,
                    signal_type=result.signal_type,
                    direction=result.direction,
                    severity=result.severity,
                    description=result.description,
                    metadata_json=metadata,
                )
                self.exchange.db.save_signal(signal)
                saved_signals.append(signal)
        return saved_signals
