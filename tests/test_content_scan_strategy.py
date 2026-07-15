"""测试 ContentScanStrategy 内容型策略。

测试覆盖：
1. 正常路径：有信号 -> 选 severity 最高 -> 写 content 动作 -> 返回非空 actions
2. 无信号 -> 返回空列表
3. 只选 1 条（不多选）
4. action_type == "content"
5. signal_ids 关联到信号
6. 冷却去重：(symbol, signal_type) 在窗口内只被选中一次
   - 同币同信号类型冷却中 -> 跳过
   - 同币不同信号类型 -> 不受冷却影响
   - 冷却过期 -> 仍可选中
   - 全部冷却中 -> 返回空（降级）
   - 冷却窗口可配置
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
from trading_service.exchange import MockExchange
from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.repository.abc import StrategyActionRecord
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
    config: ContentScanConfig | None = None,
) -> ContentScanStrategy:
    """创建带连续K线检测器的内容型策略。"""
    repo = exchange.db
    detector = ConsecutiveCandleDetector(repo=repo, client=None, interval="1d", min_streak=3)
    picker = FakePicker(picker_symbols or [])
    return ContentScanStrategy(
        exchange=exchange,
        config=config or ContentScanConfig(),
        symbol_picker=picker,
        signal_detectors=[detector],
    )


def seed_content_action(
    exchange: MockExchange,
    *,
    symbol: str,
    signal_type: str,
    created_at: datetime,
) -> None:
    """向仓库预置一条历史 content 动作（模拟该信号曾被选中发帖）。"""
    exchange.db.save_action(StrategyActionRecord(
        id=f"seed_{symbol}_{signal_type}_{created_at.isoformat()}",
        execution_id="seed",
        strategy_name="content_scan",
        action_type="content",
        symbol=symbol,
        reason_text=f"{symbol} {signal_type}",
        reason_data={"signal_type": signal_type, "direction": "bullish", "severity": 3},
        created_at=created_at,
    ))


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


class TestContentScanStrategyCooldown:
    """冷却去重测试：(symbol, signal_type) 在窗口内只被选中一次。"""

    @pytest.mark.asyncio
    async def test_same_symbol_signal_cooled_down(self, exchange: MockExchange) -> None:
        """✅ 同 (symbol, signal_type) 冷却中 -> 第二次执行跳过，返回空。"""
        # 预置：2 小时前 BTCUSDT consecutive_rise 已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        # 3 连阳 -> consecutive_rise（与历史同类型）
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec002")

        assert actions == [], "冷却中的 (symbol, signal_type) 应被跳过"

    @pytest.mark.asyncio
    async def test_same_symbol_different_signal_not_cooled(self, exchange: MockExchange) -> None:
        """✅ 同 symbol 不同 signal_type -> 不受冷却影响，仍可选中。

        这里用两个检测器：连续K线（已冷却）+ 暴涨暴跌（未冷却）。
        暴涨暴跌信号应被选中。
        """
        from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
        from trading_service.detectors.price_change import PriceChangeDetector

        # 预置：2 小时前 BTCUSDT consecutive_rise 已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        # BTC: 3 连阳（consecutive_rise，冷却中）+ 24h 暴涨 35%（price_surge，未冷却）
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price_change_pct_24h = 35.0
        repo = exchange.db
        picker = FakePicker([info])
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=picker,
            signal_detectors=[
                ConsecutiveCandleDetector(repo=repo, client=None, interval="1d", min_streak=3),
                PriceChangeDetector(repo=repo, threshold=20.0),
            ],
        )

        actions = await strategy.execute(execution_id="exec002")

        assert len(actions) == 1, "应选未冷却的 price_surge"
        db_actions = exchange.db.list_actions_by_execution("exec002")
        assert db_actions[0].reason_data["signal_type"] == "price_surge", (
            "应选 price_surge 而非冷却中的 consecutive_rise"
        )

    @pytest.mark.asyncio
    async def test_expired_cooldown_allows_selection(self, exchange: MockExchange) -> None:
        """✅ 冷却已过期（13h 前 > 默认 12h）-> 仍可选中。"""
        # 预置：13 小时前 BTCUSDT consecutive_rise 已发帖（超过 12h 窗口）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=13),
        )
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec002")

        assert len(actions) == 1, "冷却过期后应可选中"
        assert actions[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_all_cooled_returns_empty(self, exchange: MockExchange) -> None:
        """✅ 所有信号都在冷却中 -> 返回空列表（降级行为）。"""
        # 预置：2 个币的连续上涨信号都已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        seed_content_action(
            exchange, symbol="ETHUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        btc = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        eth = make_info("ETHUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [btc, eth])

        actions = await strategy.execute(execution_id="exec002")

        assert actions == [], "全部冷却中应返回空"

    @pytest.mark.asyncio
    async def test_cooldown_hours_configurable(self, exchange: MockExchange) -> None:
        """✅ cooldown_hours 可配置，改为 1h 后 2h 前的记录过期。"""
        # 预置：2 小时前 BTCUSDT consecutive_rise 已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        # cooldown_hours=1 -> 2h 前的记录已过期
        strategy = make_strategy(exchange, [info], config=ContentScanConfig(cooldown_hours=1))

        actions = await strategy.execute(execution_id="exec002")

        assert len(actions) == 1, "1h 窗口下 2h 前的记录应已过期"
        assert actions[0].symbol == "BTCUSDT"
