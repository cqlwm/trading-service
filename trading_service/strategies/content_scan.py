"""内容型策略：检测信号，选 1 条生成贴文。

不开仓、不平仓。只产出信号 + content 动作记录，触发贴文生成。
每 10 分钟从涨幅榜选币，运行信号检测器，对信号做 (symbol, signal_type, interval, kline_close_time)
四元组去重后，按 timeframe_priority 降级选 severity 最高的 1 条，写入 action_type="content"
的动作记录，使 scheduler 触发 PostGenerator。

去重机制：以信号所基于的最新已收盘 K 线收盘时间(kline_close_time) + interval 为周期标识，
同一根 K 线期间同一 (symbol, signal_type, interval) 只发一次；推进到下一根新 K 线才解锁。
interval 维度解决 UTC 日界 bug：1d/4h/1h/15m 在日界收盘时间相同时不会互相误去重。

时效性注入：run_detectors override 为每条信号 metadata 注入 kline_close_time_str
（毫秒时间戳的 ISO 字符串版，LLM 阅读用）。current_price / current_time 不注入 signal
metadata（冗余），而是放在 market_snapshot 第一层（execute 写 reason_data 时聚合），
供 PostGenerator 在 prompt 中引用，让 LLM 感知实时价与发帖频率。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.repository.abc import SignalRecord, StrategyActionRecord
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig


@dataclass
class ContentScanConfig(StrategyConfig):
    """内容型策略配置。"""

    top_n: int = 20  # 涨幅榜取前 N（由 picker 的 source 控制，此处仅记录）
    lookback_days: int = 7  # 去重查询安全边界（避免扫全表），真正去重由四元组相等决定
    # 时间框架降级链：选信号时按此顺序逐级降级，第一个有新鲜信号的 interval 选中后即停。
    # 1d 优先（粗粒度信号最重要），无 1d 才看 4h，依次降到 15m；
    # ticker 兜底（无 K 线的 24h 暴涨暴跌信号，作为最低优先级保底）。
    timeframe_priority: list[str] = field(
        default_factory=lambda: ["1d", "4h", "1h", "15m", "ticker"]
    )


class ContentScanStrategy(Strategy):
    """内容型策略：检测信号，K 线周期去重后选 1 条生成贴文。

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

    async def run_detectors(self, candidates: list[SymbolInfo]) -> list[SignalRecord]:
        """override：在基类落盘信号后，为每条信号注入 kline_close_time_str。

        current_price / current_time 不注入 signal metadata（冗余 -- 整个 market_snapshot
        是同一时刻生成的，所有信号共享同一组实时价/时间），而是放在 market_snapshot 第一层
        （execute 写 reason_data 时聚合），LLM 在 prompt 中从市场快照第一层读取。
        kline_close_time_str 把毫秒时间戳转为 ISO 字符串，方便 LLM 直观阅读 K 线收盘时间
        （原始 kline_close_time 是毫秒 int，机器用，去重 key 保留）；每条信号基于不同 K 线，
        收盘时间不同，故仍注入 signal metadata。setdefault 语义：检测器已写则不覆盖；
        kline_close_time 缺失或非数值时不注入 str。
        """
        signals = await super().run_detectors(candidates)
        for s in signals:
            kct = s.metadata_json.get("kline_close_time")
            if isinstance(kct, (int, float)) and "kline_close_time_str" not in s.metadata_json:
                s.metadata_json["kline_close_time_str"] = datetime.fromtimestamp(
                    kct / 1000, tz=timezone.utc,
                ).isoformat()
        return signals

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行内容扫描：选币 -> 信号检测 -> 周期去重 -> 按降级链选 1 条 -> 写 content 动作。"""
        # 1. 选币
        candidates = await self.symbol_picker.pick()
        if not candidates:
            return []

        # 2. 信号检测 + 落盘（run_detectors override 注入 current_price/time 到每条信号）
        signals = await self.run_detectors(candidates)
        if not signals:
            return []

        # 3. 周期去重：剔除与历史已发帖 (symbol, signal_type, interval, kline_close_time) 相同的信号
        fresh = self._filter_duplicated(signals)
        if not fresh:
            return []

        # 4. 按降级链选 1 条：timeframe_priority 逐级降级，第一个有新鲜信号的 interval
        #    组内选 severity 最高（同 severity 取最新）；全部 interval 无新鲜信号 -> 不发
        best = self._pick_by_priority(fresh)
        if best is None:
            return []

        # 5. 写 content 动作记录（触发 post_generator）
        #    market_snapshot 聚合完整市场观察上下文（当前 symbol 多周期信号 + 实时价/时间/24h涨跌），
        #    供 PostGenerator 在 prompt 中引用。走 reason_data 路径（不走 list_signals 回读），
        #    绕开 SQL 层字段丢失问题。
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
                "interval": best.metadata_json.get("interval"),
                "kline_close_time": best.metadata_json.get("kline_close_time"),
                "metadata": best.metadata_json,
                "market_snapshot": self._build_market_snapshot(best.symbol, candidates, signals),
            },
            signal_ids=[best.id],
            created_at=datetime.now(timezone.utc),
        ))

        # 6. 返回非空 actions 触发 post_generator
        return [StrategyAction(type="content", symbol=best.symbol, reason=best.description)]

    def _build_market_snapshot(
        self,
        symbol: str,
        candidates: list[SymbolInfo],
        signals: list[SignalRecord],
    ) -> dict[str, object]:
        """构建完整市场观察上下文（LLM prompt 引用）。

        聚合：实时价、当前时间、24h 涨跌幅、当前 symbol 的所有产出信号（含各检测器 metadata）。
        聚焦当前生成贴文的 symbol，只含该 symbol 在各 interval 的信号（多周期共振/分歧），
        不混入其他候选币的信号。
        检测器自治：每条信号的 metadata 就是该检测器对上下文的贡献，新检测器只需写好
        metadata 即可自动进入上下文，零改动扩展。
        signals 走内存列表（已注入 current_price/time），不经 list_signals 回读。
        """
        price_by_symbol = {info.symbol: info.price for info in candidates}
        change_by_symbol = {info.symbol: info.price_change_pct_24h for info in candidates}
        symbol_signals = [s for s in signals if s.symbol == symbol]
        return {
            "symbol": symbol,
            "current_price": price_by_symbol.get(symbol, 0.0),
            "current_time": datetime.now(timezone.utc).isoformat(),
            "price_change_pct_24h": change_by_symbol.get(symbol, 0.0),
            "signals": [self._signal_to_context(s) for s in symbol_signals],
        }

    @staticmethod
    def _signal_to_context(signal: SignalRecord) -> dict[str, object]:
        """将信号转为 prompt 上下文字典（含完整 metadata）。"""
        return {
            "signal_type": signal.signal_type,
            "direction": signal.direction,
            "severity": signal.severity,
            "description": signal.description,
            "interval": signal.metadata_json.get("interval"),
            "metadata": signal.metadata_json,
        }

    def _pick_by_priority(self, signals: list[Any]) -> Any | None:
        """按 timeframe_priority 降级链选 1 条信号。

        信号先按 metadata["interval"] 分组（缺 interval 视为 '1d'），
        再按 config.timeframe_priority 顺序遍历：第一个有信号的 interval，
        从该组选 severity 最高（同 severity 取 created_at 最新）1 条返回。
        不在降级链里的 interval 不参与选择（如 ticker 默认不在链里）。
        全部 interval 都无信号 -> 返回 None。
        """
        by_interval: dict[str, list[Any]] = {}
        for s in signals:
            iv = s.metadata_json.get("interval", "1d")
            by_interval.setdefault(iv, []).append(s)
        for iv in self.config.timeframe_priority:
            group = by_interval.get(iv)
            if group:
                return max(group, key=lambda s: (s.severity, s.created_at))
        return None

    def _filter_duplicated(self, signals: list[Any]) -> list[Any]:
        """剔除与历史已发帖 K 线周期相同的 (symbol, signal_type, interval, kline_close_time)。

        四元组去重：同一根 K 线期间同一 (symbol, signal_type, interval) 只发一次；
        推进到下一根新 K 线（kline_close_time 变化）才解锁。
        interval 维度解决 UTC 日界 bug：1d/4h/1h/15m 在日界收盘时间相同时不会互相误去重。
        旧数据缺 interval 字段视为 '1d'（升级前均为 1d 检测器）。
        since 仅作查询安全边界（避免扫全表），真正去重由四元组相等决定。
        """
        since = datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)
        recent = self.exchange.db.list_actions(
            strategy_name=self.name, action_type="content", since=since,
        )
        posted = {self._action_dedup_key(a) for a in recent}
        return [s for s in signals if self._signal_dedup_key(s) not in posted]

    @staticmethod
    def _action_dedup_key(action: Any) -> tuple[str, str, str, Any]:
        """历史动作的去重 key：缺 interval 视为 '1d'（兼容旧数据）。"""
        data = action.reason_data
        return (
            action.symbol,
            data.get("signal_type", ""),
            data.get("interval", "1d"),
            data.get("kline_close_time"),
        )

    @staticmethod
    def _signal_dedup_key(signal: Any) -> tuple[str, str, str, Any]:
        """信号的去重 key：缺 interval 视为 '1d'（兼容无 interval 的检测器）。"""
        meta = signal.metadata_json
        return (
            signal.symbol,
            signal.signal_type,
            meta.get("interval", "1d"),
            meta.get("kline_close_time"),
        )

    def get_status(self) -> dict[str, Any]:
        """返回策略状态。"""
        return {
            "strategy": self.name,
            "cron": self.cron,
            "type": "content",
            "config": {"top_n": self.config.top_n, "lookback_days": self.config.lookback_days},
        }
