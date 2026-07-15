"""内容型策略：检测信号，选 1 条生成贴文。

不开仓、不平仓。只产出信号 + content 动作记录，触发贴文生成。
每 10 分钟从涨幅榜选币，运行信号检测器，对信号做 (symbol, signal_type) 粒度的
冷却去重后，选 severity 最高的 1 条，写入 action_type="content" 的动作记录，
使 scheduler 触发 PostGenerator。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from trading_service.exchange import MockExchange
from trading_service.repository.abc import StrategyActionRecord
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.pickers import ISymbolPicker


@dataclass
class ContentScanConfig(StrategyConfig):
    """内容型策略配置。"""

    top_n: int = 20  # 涨幅榜取前 N（由 picker 的 source 控制，此处仅记录）
    cooldown_hours: int = 12  # (symbol, signal_type) 冷却窗口，避免重复发帖


class ContentScanStrategy(Strategy):
    """内容型策略：检测信号，冷却去重后选 1 条生成贴文。

    不开仓、不平仓。只产出信号 + content 动作记录，触发贴文生成。
    """

    name = "content_scan"
    cron = "0 */10 * * * *"  # 每 10 分钟

    def __init__(
        self,
        exchange: MockExchange,
        config: ContentScanConfig,
        symbol_picker: ISymbolPicker,
        signal_detectors: list[Any] | None = None,
    ) -> None:
        super().__init__(exchange, config, symbol_picker, signal_detectors)
        self.config: ContentScanConfig = config

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行内容扫描：选币 -> 信号检测 -> 冷却去重 -> 选 1 条 -> 写 content 动作。"""
        # 1. 选币
        candidates = await self.symbol_picker.pick()
        if not candidates:
            return []

        # 2. 信号检测 + 落盘
        signals = await self.run_detectors(candidates, execution_id)
        if not signals:
            return []

        # 3. 冷却去重：剔除近 cooldown_hours 内已发过帖的 (symbol, signal_type)
        fresh = self._filter_cooled(signals)
        if not fresh:
            return []

        # 4. 选 severity 最高（同 severity 取最新）
        best = max(fresh, key=lambda s: (s.severity, s.created_at))

        # 5. 写 content 动作记录（触发 post_generator）
        self.exchange.db.save_action(StrategyActionRecord(
            id=uuid.uuid4().hex[:12],
            execution_id=execution_id,
            strategy_name=self.name,
            action_type="content",
            symbol=best.symbol,
            reason_text=best.description,
            reason_data={
                "signal_type": best.signal_type,
                "direction": best.direction,
                "severity": best.severity,
                "metadata": best.metadata_json,
            },
            signal_ids=[best.id],
            created_at=datetime.now(timezone.utc),
        ))

        # 6. 返回非空 actions 触发 post_generator
        return [StrategyAction(type="content", symbol=best.symbol, reason=best.description)]

    def _filter_cooled(self, signals: list[Any]) -> list[Any]:
        """剔除近 cooldown_hours 内已发过帖的 (symbol, signal_type)。"""
        since = datetime.now(timezone.utc) - timedelta(hours=self.config.cooldown_hours)
        recent = self.exchange.db.list_actions(
            strategy_name=self.name, action_type="content", since=since,
        )
        cooled = {(a.symbol, a.reason_data.get("signal_type", "")) for a in recent}
        return [s for s in signals if (s.symbol, s.signal_type) not in cooled]

    def get_status(self) -> dict[str, Any]:
        """返回策略状态。"""
        return {
            "strategy": self.name,
            "cron": self.cron,
            "type": "content",
            "config": {"top_n": self.config.top_n, "cooldown_hours": self.config.cooldown_hours},
        }
