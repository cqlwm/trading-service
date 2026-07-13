"""内容型策略：检测连续涨跌K线，选 1 条生成贴文。

不开仓、不平仓。只产出信号 + content 动作记录，触发贴文生成。
每 10 分钟从涨幅榜选币，运行信号检测器，选 severity 最高的 1 条信号，
写入 action_type="content" 的动作记录，使 scheduler 触发 PostGenerator。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from trading_service.exchange import MockExchange
from trading_service.repository.abc import StrategyActionRecord
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.pickers import ISymbolPicker


class ContentScanConfig(StrategyConfig):
    """内容型策略配置。"""

    top_n: int = 20  # 涨幅榜取前 N（由 picker 的 source 控制，此处仅记录）


class ContentScanStrategy(Strategy):
    """内容型策略：检测连续涨跌K线，选 1 条生成贴文。

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
        """执行内容扫描：选币 -> 信号检测 -> 选 1 条 -> 写 content 动作。"""
        # 1. 选币
        candidates = await self.symbol_picker.pick()
        if not candidates:
            return []

        # 2. 信号检测 + 落盘
        signals = await self.run_detectors(candidates, execution_id)
        if not signals:
            return []

        # 3. 选 severity 最高的 1 条
        best = max(signals, key=lambda s: s.severity)

        # 4. 写 content 动作记录（触发 post_generator）
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

        # 5. 返回非空 actions 触发 post_generator
        return [StrategyAction(type="content", symbol=best.symbol, reason=best.description)]

    def get_status(self) -> dict[str, Any]:
        """返回策略状态。"""
        return {
            "strategy": self.name,
            "cron": self.cron,
            "type": "content",
            "config": {"top_n": self.config.top_n},
        }
