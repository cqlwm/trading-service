from __future__ import annotations
from typing import Any

from dataclasses import dataclass

from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.detectors.base import SignalDetector
from trading_service.types import TradeDirection


@dataclass
class MicroCapConfig(StrategyConfig):
    """微市值策略配置。"""

    max_positions: int = 10
    position_size_usdt: float = 10.0
    take_profit_pct: float = 5.0
    stop_loss_pct: float = 15.0
    min_volume_usdt: float = 1_000_000
    max_market_cap: float = 50_000_000


class MicroCapStrategy(Strategy):
    """微市值做多策略。

    选币（由 SymbolPicker 完成）：市值低于 5000 万、昨日上涨的代币。
    入场：技术分析显示横盘或近期突破（金叉）时，买入 position_size_usdt。
    """

    name = "micro_cap"
    cron = "0 * * * * *"  # 6字段：秒 分 时 日 月 周 = 每分钟

    def __init__(
        self,
        exchange: MockExchange,
        config: MicroCapConfig,
        symbol_picker: ISymbolPicker,
        signal_detectors: list[SignalDetector] | None = None,
    ) -> None:
        super().__init__(exchange, config, symbol_picker, signal_detectors)
        self.config: MicroCapConfig = config

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        """执行策略 - 选币 + 信号检测 + 信号驱动入场。

        1. 选币：symbol_picker.pick() 获取候选币
        2. 信号检测：检测器产出信号落盘
        3. 决策：从 DB 拉取金叉信号，排除已持仓 symbol 后开仓
        """
        actions: list[StrategyAction] = []
        positions = self.exchange.get_positions(tag="micro_cap", status="open")
        current_count = len(positions)

        if current_count >= self.config.max_positions:
            return actions

        # 1. 选币
        candidates = await self.symbol_picker.pick()
        # 2. 信号检测（落盘到 trading_signals）
        await self.run_detectors(candidates, execution_id)
        # 3. 从 DB 拉取金叉信号决策
        actions.extend(await self._open_from_signals(current_count, execution_id))
        return actions

    async def _open_from_signals(self, current_count: int, execution_id: str = "") -> list[StrategyAction]:
        """从数据库拉取金叉信号，开新仓。"""
        actions: list[StrategyAction] = []
        # 拉取最近的金叉信号
        signals = self.get_recent_signals(signal_type="golden_cross", limit=20)

        occupied = {
            p.symbol for p in self.exchange.get_positions(tag="micro_cap", status="open")
        }
        # 排除已有持仓的 symbol
        candidate_signals = [s for s in signals if s.symbol not in occupied]

        if not candidate_signals:
            return actions

        slots = self.config.max_positions - current_count
        prices = await self.exchange.fetch_prices([s.symbol for s in candidate_signals[:slots]])

        for signal in candidate_signals[:slots]:
            price = prices.get(signal.symbol, 0.0)
            if price > 0:
                # 取出选币时定格的市值快照（由 run_detectors 注入信号 metadata）
                cap_raw = signal.metadata_json.get("market_cap", 0.0)
                market_cap = float(cap_raw) if isinstance(cap_raw, (int, float)) else 0.0
                self.exchange.open_position(
                    symbol=signal.symbol,
                    direction=TradeDirection.LONG,
                    size=self.config.position_size_usdt,
                    price=price,
                    tag="micro_cap",
                    reason_text=f"金叉信号开仓 @ {price}",
                    reason_data={
                        "action": "entry_breakout",
                        "signal_type": signal.signal_type,
                        "price": price,
                        "size": self.config.position_size_usdt,
                    },
                    signal_ids=[signal.id],
                    execution_id=execution_id,
                    market_cap=market_cap,
                )
                actions.append(StrategyAction(
                    type="open",
                    symbol=signal.symbol,
                    reason=f"金叉信号开仓 @ {price}",
                ))
        return actions

    def get_status(self) -> dict[str, Any]:
        """获取策略状态。"""
        positions = self.exchange.get_positions(tag="micro_cap")
        return {
            "config": {
                "max_positions": self.config.max_positions,
                "position_size_usdt": self.config.position_size_usdt,
                "take_profit_pct": self.config.take_profit_pct,
                "stop_loss_pct": self.config.stop_loss_pct,
                "min_volume_usdt": self.config.min_volume_usdt,
                "max_market_cap": self.config.max_market_cap,
            },
            "open_positions": len([p for p in positions if p.status == "open"]),
            "total_positions": len(positions),
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取历史记录。"""
        positions = self.exchange.get_positions(tag="micro_cap")
        return [
            {
                "symbol": p.symbol,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "status": p.status,
                "pnl_pct": p.final_pnl_pct if p.final_pnl_pct else 0.0,
                "created_at": p.created_at.isoformat(),
            }
            for p in positions[:limit]
        ]
