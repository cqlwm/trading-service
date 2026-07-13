"""测试 ContentScanStrategy 内容型策略。

测试覆盖：
1. 正常路径：有信号 -> 选 severity 最高 -> 写 content 动作 -> 返回非空 actions
2. 无信号 -> 返回空列表
3. 只选 1 条（不多选）
4. action_type == "content"
5. signal_ids 关联到信号
"""
from __future__ import annotations

import pandas as pd
import pytest

from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.strategies.content_scan import ContentScanConfig, ContentScanStrategy


class FakePicker(ISymbolPicker):
    """返回预置候选币的选币器。"""

    def __init__(self, symbols: list[SymbolInfo]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        return list(self.symbols)


from typing import Sequence
def make_klines_df(candles: Sequence[tuple[int | float, int | float]]) -> pd.DataFrame:
    n = len(candles)
    return pd.DataFrame({
        "datetime": list(range(n)),
        "open": [c[0] for c in candles],
        "high": [max(c[0], c[1]) for c in candles],
        "low": [min(c[0], c[1]) for c in candles],
        "close": [c[1] for c in candles],
        "volume": [100.0] * n,
    })


def make_info(symbol: str, candles: Sequence[tuple[int | float, int | float]]) -> SymbolInfo:
    info = SymbolInfo(symbol=symbol)
    info.klines["1d"] = make_klines_df(candles)
    return info


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    return MockExchange(InMemoryTradingRepository())


def make_strategy(
    exchange: MockExchange,
    picker_symbols: list[SymbolInfo] | None = None,
) -> ContentScanStrategy:
    """创建带连续K线检测器的内容型策略。"""
    repo = exchange.db
    detector = ConsecutiveCandleDetector(repo=repo, client=None, interval="1d", min_streak=3)
    picker = FakePicker(picker_symbols or [])
    return ContentScanStrategy(
        exchange=exchange,
        config=ContentScanConfig(),
        symbol_picker=picker,
        signal_detectors=[detector],
    )


class TestContentScanStrategyNormal:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_signal_produces_content_action(self, exchange: MockExchange) -> None:
        """✅ 有信号 -> 选 severity 最高 -> 写 content 动作 -> 返回非空 actions。"""
        # 3 连阳 -> consecutive_rise, severity=3
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec001")

        assert len(actions) == 1
        assert actions[0].type == "content"
        assert actions[0].symbol == "BTCUSDT"

        # 验证动作记录已落盘
        db_actions = exchange.db.list_actions_by_execution("exec001")
        assert len(db_actions) == 1
        assert db_actions[0].action_type == "content"
        assert db_actions[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_signal_ids_links_to_signal(self, exchange: MockExchange) -> None:
        """✅ 动作记录的 signal_ids 应关联到落盘的信号。"""
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        await strategy.execute(execution_id="exec001")

        db_actions = exchange.db.list_actions_by_execution("exec001")
        assert len(db_actions[0].signal_ids) == 1, "应关联 1 个信号 ID"

        # 验证信号确实落盘了
        signals = exchange.db.list_signals(symbol="BTCUSDT")
        assert len(signals) >= 1
        assert db_actions[0].signal_ids[0] == signals[0].id


class TestContentScanStrategyNoSignal:
    """无信号场景测试。"""

    @pytest.mark.asyncio
    async def test_no_signal_returns_empty(self, exchange: MockExchange) -> None:
        """✅ 无信号 -> 返回空列表。"""
        # 涨跌交替 -> 无连续
        info = make_info("BTCUSDT", [(10, 11), (11, 10), (10, 11)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec001")

        assert actions == [], "无信号应返回空列表"

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self, exchange: MockExchange) -> None:
        """✅ 空候选列表 -> 返回空列表。"""
        strategy = make_strategy(exchange, [])

        actions = await strategy.execute(execution_id="exec001")

        assert actions == []


class TestContentScanStrategySelection:
    """信号选择逻辑测试。"""

    @pytest.mark.asyncio
    async def test_selects_highest_severity(self, exchange: MockExchange) -> None:
        """✅ 多个信号 -> 选 severity 最高的 1 条。"""
        # BTC: 3 连阳 -> severity=3
        btc = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        # ETH: 5 连阳 -> severity=5
        eth = make_info("ETHUSDT", [(10, 11), (11, 12), (12, 13), (13, 14), (14, 15)])
        strategy = make_strategy(exchange, [btc, eth])

        actions = await strategy.execute(execution_id="exec001")

        assert len(actions) == 1, "只选 1 条"
        assert actions[0].symbol == "ETHUSDT", "应选 severity=5 的 ETH"

    @pytest.mark.asyncio
    async def test_only_one_action_record(self, exchange: MockExchange) -> None:
        """✅ 只写 1 条动作记录（不多写）。"""
        btc = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        eth = make_info("ETHUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [btc, eth])

        await strategy.execute(execution_id="exec001")

        db_actions = exchange.db.list_actions_by_execution("exec001")
        assert len(db_actions) == 1, "只应写 1 条动作记录"
