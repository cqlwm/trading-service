"""测试 ContentScanStrategy 内容型策略。

测试覆盖：
1. 正常路径：有信号 -> 选 severity 最高 -> 写 content 动作 -> 返回非空 actions
2. 无信号 -> 返回空列表
3. 只选 1 条（不多选）
4. action_type == "content"
5. signal_ids 关联到信号
6. K 线周期去重：(symbol, signal_type, kline_close_time) 相同则跳过
   - 同 K 线周期已发过 -> 跳过
   - 新 K 线周期 -> 解锁可发
   - 同币不同信号类型 -> 不受影响
   - 全部已发过 -> 返回空（降级）
   - 旧数据无 kline_close_time -> 不阻塞新发帖
"""
from __future__ import annotations

from datetime import datetime, timezone

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


def make_info_multi(
    symbol: str, klines_by_interval: dict[str, Sequence[tuple[int | float, int | float]]],
) -> SymbolInfo:
    """构造多周期 klines 的 SymbolInfo，key 为 interval（如 '1d'/'4h'）。"""
    info = SymbolInfo(symbol=symbol)
    for interval, candles in klines_by_interval.items():
        info.klines[interval] = make_klines_df(candles)
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
    kline_close_time: int,
    interval: str = "1d",
    created_at: datetime | None = None,
) -> None:
    """向仓库预置一条历史 content 动作（模拟该信号曾被选中发帖）。

    kline_close_time 为发帖时信号所基于的 K 线周期标识。
    interval 为发帖时信号所基于的时间框架（默认 "1d"，兼容历史数据）。
    created_at 默认为当前时间（在 lookback_days 安全边界内）。
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    exchange.db.save_action(StrategyActionRecord(
        id=f"seed_{symbol}_{signal_type}_{interval}_{kline_close_time}",
        execution_id="seed",
        strategy_name="content_scan",
        action_type="content",
        symbol=symbol,
        reason_text=f"{symbol} {signal_type}",
        reason_data={
            "signal_type": signal_type,
            "direction": "bullish",
            "severity": 3,
            "interval": interval,
            "kline_close_time": kline_close_time,
        },
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


class TestContentScanStrategyDedup:
    """K 线周期去重测试：(symbol, signal_type, kline_close_time) 相同则跳过。

    测试用 make_klines_df 的 datetime 列为 range(n)，3 根 K 线时
    kline_close_time = df["datetime"].iloc[-1] = 2。
    """

    @pytest.mark.asyncio
    async def test_same_kline_period_skipped(self, exchange: MockExchange) -> None:
        """✅ 同 (symbol, signal_type, kline_close_time) -> 已发过，跳过返回空。"""
        # 3 连阳 -> kline_close_time=2，预置同周期已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            kline_close_time=2,
        )
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec002")

        assert actions == [], "同 K 线周期已发过的信号应被跳过"

    @pytest.mark.asyncio
    async def test_new_kline_period_unlocks(self, exchange: MockExchange) -> None:
        """✅ kline_close_time 不同（新 K 线）-> 可选中。"""
        # 预置：上一根 K 线(kline_close_time=1)已发帖
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            kline_close_time=1,
        )
        # 当前最新已收盘 K 线 kline_close_time=2（3 根 K 线）
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec002")

        assert len(actions) == 1, "新 K 线周期应解锁"
        assert actions[0].symbol == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_same_symbol_different_signal_not_duplicated(self, exchange: MockExchange) -> None:
        """✅ 同 symbol 不同 signal_type -> 不受去重影响，仍可选中。

        连续K线（已发过）+ 暴涨暴跌（未发过），暴涨暴跌应被选中。
        """
        from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
        from trading_service.detectors.price_change import PriceChangeDetector

        # 预置：BTCUSDT consecutive_rise 已发帖（kline_close_time=2，与当前相同）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            kline_close_time=2,
        )
        # BTC: 3 连阳（consecutive_rise，去重命中）+ 24h 暴涨 35%（price_surge，未发过）
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

        assert len(actions) == 1, "应选未去重的 price_surge"
        db_actions = exchange.db.list_actions_by_execution("exec002")
        assert db_actions[0].reason_data["signal_type"] == "price_surge", (
            "应选 price_surge 而非已发过的 consecutive_rise"
        )

    @pytest.mark.asyncio
    async def test_all_duplicated_returns_empty(self, exchange: MockExchange) -> None:
        """✅ 所有信号都已发过 -> 返回空列表（降级行为）。"""
        # 预置：2 个币的连续上涨信号都已发帖（同 kline_close_time=2）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="consecutive_rise",
            kline_close_time=2,
        )
        seed_content_action(
            exchange, symbol="ETHUSDT", signal_type="consecutive_rise",
            kline_close_time=2,
        )
        btc = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        eth = make_info("ETHUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [btc, eth])

        actions = await strategy.execute(execution_id="exec002")

        assert actions == [], "全部已发过应返回空"

    @pytest.mark.asyncio
    async def test_legacy_action_without_kline_close_time_not_blocking(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 旧数据无 kline_close_time 字段 -> 不命中去重，不阻塞新发帖。"""
        # 预置一条旧格式动作（无 kline_close_time 字段，模拟历史数据）
        exchange.db.save_action(StrategyActionRecord(
            id="legacy_1",
            execution_id="legacy",
            strategy_name="content_scan",
            action_type="content",
            symbol="BTCUSDT",
            reason_text="历史贴文",
            reason_data={"signal_type": "consecutive_rise", "direction": "bullish", "severity": 3},
            created_at=datetime.now(timezone.utc),
        ))
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec002")

        assert len(actions) == 1, "旧数据无 kline_close_time 不应阻塞新信号"


class TestContentScanStrategyIntervalDedup:
    """四元组去重测试：(symbol, signal_type, interval, kline_close_time)。

    修复 UTC 日界 bug：1d/4h/1h/15m 在 UTC 00:00 时 kline_close_time 可能完全相等，
    若去重 key 不含 interval，会误把其他周期的信号当成已发过滤掉。
    """

    @pytest.mark.asyncio
    async def test_same_kline_close_time_different_interval_not_duplicated(
        self, exchange: MockExchange,
    ) -> None:
        """✅ kline_close_time 相同但 interval 不同 -> 不互斥，4h 信号可发。

        场景：UTC 日界，1d 和 4h 的最近已收盘 K 线收盘时间恰好相同（都是上一日 23:59:59.999）。
        预置 1d 已发 -> 当前 4h 信号不应被去重。
        """
        from trading_service.detectors.breakout import BreakoutDetector

        # 预置：1d breakout_high 已发帖，kline_close_time=999（模拟日界对齐）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="breakout_high",
            interval="1d", kline_close_time=999,
        )

        # 当前：4h breakout_high 信号，kline_close_time 恰好也是 999（日界对齐）
        # 用 6 根 K 线构造突破新高：前 5 根高点 15，第 6 根 close=16 突破
        candles = [(10, 12), (11, 13), (12, 14), (11, 15), (13, 15), (14, 16)]
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines["4h"] = make_klines_df(candles)
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=[
                BreakoutDetector(repo=repo, client=None, interval="4h", window=5),
            ],
        )

        actions = await strategy.execute(execution_id="exec010")

        # 关键断言：4h 信号不应被 1d 历史去重
        assert len(actions) == 1, (
            "kline_close_time 相同但 interval 不同时，4h 信号不应被 1d 历史去重"
        )
        db_actions = exchange.db.list_actions_by_execution("exec010")
        assert db_actions[0].reason_data["interval"] == "4h", (
            f"应发 4h 信号，实际 interval={db_actions[0].reason_data.get('interval')}"
        )

    @pytest.mark.asyncio
    async def test_same_interval_same_kline_close_time_still_deduped(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 同 interval 同 kline_close_time -> 仍应被去重（四元组完整相等）。"""
        from trading_service.detectors.breakout import BreakoutDetector

        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="breakout_high",
            interval="4h", kline_close_time=5,
        )
        # 6 根 K 线，kline_close_time=5，与预置相同
        candles = [(10, 12), (11, 13), (12, 14), (11, 15), (13, 15), (14, 16)]
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines["4h"] = make_klines_df(candles)
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=[
                BreakoutDetector(repo=repo, client=None, interval="4h", window=5),
            ],
        )

        actions = await strategy.execute(execution_id="exec011")

        assert actions == [], "同 interval 同 kline_close_time 应被去重"

    @pytest.mark.asyncio
    async def test_legacy_action_without_interval_treated_as_1d(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 旧数据缺 interval 字段 -> 视为 '1d'，1d 新信号应被去重。

        历史已发的 content 动作 reason_data 没有 interval 字段（升级前数据）。
        升级后应把缺失的 interval 视为 '1d'，与当前 1d 信号命中去重。
        """
        # 预置旧格式动作：无 interval 字段
        exchange.db.save_action(StrategyActionRecord(
            id="legacy_no_interval",
            execution_id="legacy",
            strategy_name="content_scan",
            action_type="content",
            symbol="BTCUSDT",
            reason_text="历史贴文（无 interval）",
            reason_data={
                "signal_type": "consecutive_rise",
                "direction": "bullish",
                "severity": 3,
                "kline_close_time": 2,
            },
            created_at=datetime.now(timezone.utc),
        ))
        # 当前 1d consecutive_rise 信号，kline_close_time=2（与历史相同）
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec012")

        assert actions == [], (
            "旧数据缺 interval 应视为 1d，与当前 1d 信号命中去重"
        )


class TestContentScanStrategyCurrentPriceTime:
    """current_price / current_time 位置 + kline_close_time_str 注入测试。

    设计：current_price / current_time 不注入 signal metadata（避免冗余 -- 整个
    market_snapshot 是同一时刻生成的，所有信号共享同一组实时价/时间），而是放在
    market_snapshot 第一层（LLM 看一眼即可，不重复散落在每条信号里）。
    kline_close_time_str 仍注入 signal metadata（每条信号基于不同 K 线，收盘时间不同）。
    """

    @pytest.mark.asyncio
    async def test_signal_metadata_not_contains_current_price_time(
        self, exchange: MockExchange,
    ) -> None:
        """✅ signal metadata 不应含 current_price / current_time（冗余，已移至 market_snapshot 第一层）。"""
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        strategy = make_strategy(exchange, [info])

        signals = await strategy.run_detectors([info])

        assert len(signals) == 1
        meta = signals[0].metadata_json
        assert "current_price" not in meta, (
            "signal metadata 不应含 current_price（冗余，已移至 market_snapshot 第一层）"
        )
        assert "current_time" not in meta, (
            "signal metadata 不应含 current_time（冗余，已移至 market_snapshot 第一层）"
        )

    @pytest.mark.asyncio
    async def test_detector_current_price_not_overwritten_by_strategy(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 检测器自己写的 current_price 保留（策略不再注入，自然不会覆盖）。"""
        from trading_service.detectors.base import SignalDetector, SignalResult

        class FakeDetectorWithPrice(SignalDetector):
            name = "fake_with_price"

            async def detect(self, candidates):
                return [SignalResult(
                    symbol="BTCUSDT",
                    signal_type="fake_signal",
                    direction="bullish",
                    severity=3,
                    description="fake",
                    metadata={"interval": "1d", "kline_close_time": 100, "current_price": 999.0},
                )]

        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=[FakeDetectorWithPrice(repo=repo)],
        )

        signals = await strategy.run_detectors([info])

        assert len(signals) == 1
        # 检测器自己写的 current_price 保留（策略不注入，不会覆盖）
        assert signals[0].metadata_json["current_price"] == 999.0

    @pytest.mark.asyncio
    async def test_market_snapshot_first_layer_contains_current_price_time(
        self, exchange: MockExchange,
    ) -> None:
        """✅ market_snapshot 第一层应含 current_price / current_time（LLM 在此读取）。"""
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec020")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec020")
        from typing import cast
        snapshot = cast(dict[str, object], db_actions[0].reason_data["market_snapshot"])
        assert snapshot["current_price"] == 50000.0, (
            "market_snapshot 第一层应含 current_price"
        )
        assert "current_time" in snapshot, "market_snapshot 第一层应含 current_time"

    @pytest.mark.asyncio
    async def test_run_detectors_injects_kline_close_time_str(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 信号 metadata 应注入 kline_close_time_str（ISO 字符串，LLM 阅读用）。

        kline_close_time 是毫秒时间戳（机器用，去重 key），LLM 难以直观理解。
        kline_close_time_str 是 ISO 字符串（如 "2026-07-19T10:00:00+00:00"），LLM 直接可读。
        注入点：run_detectors override（与 current_price/time 同机制）。
        """
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        strategy = make_strategy(exchange, [info])

        signals = await strategy.run_detectors([info])

        assert len(signals) == 1
        meta = signals[0].metadata_json
        assert "kline_close_time" in meta, "信号应含原始 kline_close_time（毫秒，去重用）"
        assert "kline_close_time_str" in meta, (
            "信号应注入 kline_close_time_str（ISO 字符串，LLM 阅读用）"
        )
        # kline_close_time_str 应为可解析的 ISO 字符串
        from datetime import datetime
        from typing import cast
        kct_str = cast(str, meta["kline_close_time_str"])
        parsed = datetime.fromisoformat(kct_str)  # 不抛异常即通过
        # 与毫秒时间戳对应同一时刻（允许时区表达差异，比对 epoch 秒）
        kct_ms = cast(int, meta["kline_close_time"])
        assert int(parsed.timestamp() * 1000) == kct_ms, (
            f"kline_close_time_str 应与 kline_close_time 同一时刻，"
            f"str={kct_str} -> {int(parsed.timestamp() * 1000)}ms，ms={kct_ms}"
        )

    @pytest.mark.asyncio
    async def test_kline_close_time_str_not_overwrite_detector_existing(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 检测器已写 kline_close_time_str -> setdefault 不覆盖。"""
        from trading_service.detectors.base import SignalDetector, SignalResult

        class FakeDetectorWithKctStr(SignalDetector):
            name = "fake_with_kct_str"

            async def detect(self, candidates):
                return [SignalResult(
                    symbol="BTCUSDT",
                    signal_type="fake_signal",
                    direction="bullish",
                    severity=3,
                    description="fake",
                    metadata={
                        "interval": "1d",
                        "kline_close_time": 100,
                        "kline_close_time_str": "CUSTOM",
                    },
                )]

        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=[FakeDetectorWithKctStr(repo=repo)],
        )

        signals = await strategy.run_detectors([info])

        assert len(signals) == 1
        assert signals[0].metadata_json["kline_close_time_str"] == "CUSTOM", (
            "检测器已写的 kline_close_time_str 不应被覆盖"
        )

    @pytest.mark.asyncio
    async def test_kline_close_time_str_skipped_when_no_kline_close_time(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 信号无 kline_close_time 时不注入 str（避免无意义的转换）。"""
        from trading_service.detectors.base import SignalDetector, SignalResult

        class FakeDetectorNoKct(SignalDetector):
            name = "fake_no_kct"

            async def detect(self, candidates):
                return [SignalResult(
                    symbol="BTCUSDT",
                    signal_type="fake_signal",
                    direction="bullish",
                    severity=3,
                    description="fake",
                    metadata={"interval": "1d"},  # 无 kline_close_time
                )]

        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=[FakeDetectorNoKct(repo=repo)],
        )

        signals = await strategy.run_detectors([info])

        assert len(signals) == 1
        # 无 kline_close_time 时不应注入 str（避免对 None/缺失做无意义转换）
        assert "kline_close_time_str" not in signals[0].metadata_json


# 突破新高 K 线样本：6 根，前 5 根高点 15，第 6 根 close=16 突破前高
_BREAKOUT_CANDLES = [(10, 12), (11, 13), (12, 14), (11, 15), (13, 15), (14, 16)]


class TestContentScanStrategyTimeframePriority:
    """时间框架降级链测试：按 timeframe_priority 顺序逐级降级选信号。

    1d 优先（粗粒度信号最重要），无 1d 才看 4h，依次降到 15m。
    每个 interval 独立去重（四元组），1d 被去重不影响 4h 可发。
    """

    def _make_multi_interval_strategy(
        self,
        exchange: MockExchange,
        info: SymbolInfo,
        intervals: list[str],
        config: ContentScanConfig | None = None,
    ) -> ContentScanStrategy:
        """构造注入多个 interval breakout 检测器的策略。"""
        from trading_service.detectors.breakout import BreakoutDetector
        repo = exchange.db
        detectors = [
            BreakoutDetector(repo=repo, client=None, interval=iv, window=5)
            for iv in intervals
        ]
        return ContentScanStrategy(
            exchange=exchange,
            config=config or ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=detectors,
        )

    @pytest.mark.asyncio
    async def test_timeframe_priority_1d_first(self, exchange: MockExchange) -> None:
        """✅ 1d 和 4h 都有信号 -> 发 1d（降级链优先级最高）。"""
        # 同一组 K 线同时挂在 1d 和 4h，两个检测器都会触发 breakout_high
        info = make_info_multi("BTCUSDT", {"1d": _BREAKOUT_CANDLES, "4h": _BREAKOUT_CANDLES})
        config = ContentScanConfig(timeframe_priority=["1d", "4h"])
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"], config)

        actions = await strategy.execute(execution_id="exec030")

        assert len(actions) == 1, "应只发 1 条"
        db_actions = exchange.db.list_actions_by_execution("exec030")
        assert db_actions[0].reason_data["interval"] == "1d", (
            f"降级链应优先发 1d，实际 interval={db_actions[0].reason_data.get('interval')}"
        )

    @pytest.mark.asyncio
    async def test_fallback_to_4h_when_1d_no_signal(self, exchange: MockExchange) -> None:
        """✅ 1d 无信号，4h 有信号 -> 发 4h（降级）。"""
        # 1d 只有 5 根 K 线，不满足 breakout 的 window+1=6 最低要求 -> 无信号
        no_breakout_1d = [(10, 11), (11, 12), (12, 13), (13, 14), (14, 15)]
        info = make_info_multi("BTCUSDT", {"1d": no_breakout_1d, "4h": _BREAKOUT_CANDLES})
        config = ContentScanConfig(timeframe_priority=["1d", "4h"])
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"], config)

        actions = await strategy.execute(execution_id="exec031")

        assert len(actions) == 1, "1d 无信号应降级到 4h"
        db_actions = exchange.db.list_actions_by_execution("exec031")
        assert db_actions[0].reason_data["interval"] == "4h", "应发 4h 信号"

    @pytest.mark.asyncio
    async def test_fallback_to_4h_when_1d_deduped(self, exchange: MockExchange) -> None:
        """✅ 1d 信号已发（被去重），4h 信号新鲜 -> 发 4h（不是不发）。"""
        # 预置 1d breakout_high 已发（kline_close_time=5，与当前 1d K 线相同）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="breakout_high",
            interval="1d", kline_close_time=5,
        )
        # 1d 和 4h 都触发突破，kline_close_time 都是 5（make_klines_df 的 datetime=range(n)）
        info = make_info_multi("BTCUSDT", {"1d": _BREAKOUT_CANDLES, "4h": _BREAKOUT_CANDLES})
        config = ContentScanConfig(timeframe_priority=["1d", "4h"])
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"], config)

        actions = await strategy.execute(execution_id="exec032")

        assert len(actions) == 1, "1d 被去重应降级到 4h，而非不发"
        db_actions = exchange.db.list_actions_by_execution("exec032")
        assert db_actions[0].reason_data["interval"] == "4h", "应发 4h 信号"

    @pytest.mark.asyncio
    async def test_all_intervals_deduped_returns_empty(self, exchange: MockExchange) -> None:
        """✅ 1d/4h 信号全部已发 -> 返回空（降级到底仍无新鲜信号）。"""
        # 预置 1d 和 4h 都已发（kline_close_time=5）
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="breakout_high",
            interval="1d", kline_close_time=5,
        )
        seed_content_action(
            exchange, symbol="BTCUSDT", signal_type="breakout_high",
            interval="4h", kline_close_time=5,
        )
        info = make_info_multi("BTCUSDT", {"1d": _BREAKOUT_CANDLES, "4h": _BREAKOUT_CANDLES})
        config = ContentScanConfig(timeframe_priority=["1d", "4h"])
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"], config)

        actions = await strategy.execute(execution_id="exec033")

        assert actions == [], "所有 interval 都被去重应返回空"

    @pytest.mark.asyncio
    async def test_pick_highest_severity_within_same_interval(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 同 interval 组内多个信号 -> 选 severity 最高（同 severity 取最新）。"""
        from trading_service.detectors.breakout import BreakoutDetector
        from trading_service.detectors.price_change import PriceChangeDetector

        # 4h breakout（severity=3）+ price_surge 80%（severity=5，interval=ticker）
        # 但 ticker 不在降级链里，所以这里测同 interval 内多信号用两个 4h 检测器
        # 改用：4h breakout（severity=3）+ 4h consecutive（severity 视连阳数）
        # 简化：注入两个 4h breakout 检测器（不同 window），都触发，severity 都是 3
        # 为避免退化为"同 severity 取最新"，用 price_change（severity=5）+ 4h breakout（severity=3）
        # 但 price_change 的 interval=ticker 不在 ["1d","4h"] 链里 -> 不会被选
        # 因此本测试改链为 ["4h","ticker"]，验证 4h 组内选 severity 最高
        info = make_info_multi("BTCUSDT", {"4h": _BREAKOUT_CANDLES})
        info.price_change_pct_24h = 80.0  # price_surge severity=5
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(timeframe_priority=["4h", "ticker"]),
            symbol_picker=FakePicker([info]),
            signal_detectors=[
                BreakoutDetector(repo=repo, client=None, interval="4h", window=5),  # severity=3
                PriceChangeDetector(repo=repo, threshold=20.0),  # severity=5, interval=ticker
            ],
        )

        actions = await strategy.execute(execution_id="exec034")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec034")
        # 4h 组只有 breakout（severity=3），应选它（ticker 在 4h 之后）
        assert db_actions[0].reason_data["interval"] == "4h"
        assert db_actions[0].reason_data["signal_type"] == "breakout_high"

    @pytest.mark.asyncio
    async def test_timeframe_priority_order_respected(
        self, exchange: MockExchange,
    ) -> None:
        """✅ 自定义降级链顺序 -> 按配置顺序选（如 ['4h','1d'] 则 4h 优先）。"""
        info = make_info_multi("BTCUSDT", {"1d": _BREAKOUT_CANDLES, "4h": _BREAKOUT_CANDLES})
        # 反向降级链：4h 优先
        config = ContentScanConfig(timeframe_priority=["4h", "1d"])
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"], config)

        actions = await strategy.execute(execution_id="exec035")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec035")
        assert db_actions[0].reason_data["interval"] == "4h", (
            "降级链 ['4h','1d'] 应优先发 4h"
        )


class TestContentScanStrategyMarketSnapshot:
    """market_snapshot 上下文测试。

    ContentScanStrategy.execute 应在 reason_data 中聚合 market_snapshot，含：
    - 所有产出信号（不只 best，让 LLM 看到多周期共振/分歧）
    - 实时价（SymbolInfo.price）、当前时间、24h 涨跌幅
    - 每条信号的完整 metadata（检测器自治：各检测器贡献的指标都在 metadata 里）

    设计意图：让 LLM 拥有完整市场观察上下文，而非只有选中的 1 条 best 信号。
    数据走 reason_data 路径（不走 list_signals 回读），绕开 SQL 层字段丢失问题。
    """

    def _make_multi_interval_strategy(
        self,
        exchange: MockExchange,
        info: SymbolInfo,
        intervals: list[str],
        config: ContentScanConfig | None = None,
    ) -> ContentScanStrategy:
        """构造注入多个 interval breakout 检测器的策略。"""
        from trading_service.detectors.breakout import BreakoutDetector
        repo = exchange.db
        detectors = [
            BreakoutDetector(repo=repo, client=None, interval=iv, window=5)
            for iv in intervals
        ]
        return ContentScanStrategy(
            exchange=exchange,
            config=config or ContentScanConfig(),
            symbol_picker=FakePicker([info]),
            signal_detectors=detectors,
        )

    @pytest.mark.asyncio
    async def test_market_snapshot_contains_all_signals(
        self, exchange: MockExchange,
    ) -> None:
        """✅ market_snapshot.signals 应含所有产出信号（不只 best 1 条）。"""
        # 1d + 4h 都触发 breakout_high -> 2 条信号，但 best 只选 1 条
        info = make_info_multi("BTCUSDT", {"1d": _BREAKOUT_CANDLES, "4h": _BREAKOUT_CANDLES})
        strategy = self._make_multi_interval_strategy(exchange, info, ["1d", "4h"])

        actions = await strategy.execute(execution_id="exec040")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec040")
        from typing import cast
        snapshot = cast(dict[str, object], db_actions[0].reason_data["market_snapshot"])
        assert "signals" in snapshot, "market_snapshot 应含 signals 列表"
        signals_list = cast(list[dict[str, object]], snapshot["signals"])
        assert len(signals_list) == 2, (
            f"应含所有 2 条产出信号（1d+4h），实际={len(signals_list)}"
        )
        # 每条信号应含 interval（来自检测器 metadata）
        intervals_in_snapshot = {s["interval"] for s in signals_list}
        assert intervals_in_snapshot == {"1d", "4h"}, (
            f"应含 1d 和 4h 两个 interval，实际={intervals_in_snapshot}"
        )

    @pytest.mark.asyncio
    async def test_market_snapshot_contains_price_time_change(
        self, exchange: MockExchange,
    ) -> None:
        """✅ market_snapshot 应含 current_price / current_time / price_change_pct_24h。"""
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        info.price_change_pct_24h = 35.0
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec041")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec041")
        from typing import cast
        snapshot = cast(dict[str, object], db_actions[0].reason_data["market_snapshot"])
        assert snapshot["symbol"] == "BTCUSDT"
        assert snapshot["current_price"] == 50000.0, (
            f"current_price 应为 SymbolInfo.price=50000.0，实际={snapshot.get('current_price')}"
        )
        assert snapshot["price_change_pct_24h"] == 35.0, (
            f"price_change_pct_24h 应为 35.0，实际={snapshot.get('price_change_pct_24h')}"
        )
        assert "current_time" in snapshot, "market_snapshot 应含 current_time"
        from datetime import datetime
        datetime.fromisoformat(cast(str, snapshot["current_time"]))  # 可解析即通过

    @pytest.mark.asyncio
    async def test_market_snapshot_signals_contain_kline_close_time_str(
        self, exchange: MockExchange,
    ) -> None:
        """✅ market_snapshot.signals[].metadata 应含 kline_close_time_str（走 reason_data 不丢失）。

        current_price/current_time 不在 signal metadata（移至 market_snapshot 第一层避免冗余）。
        kline_close_time_str 仍注入 signal metadata（每条信号 K 线收盘时间不同）。
        验证走 reason_data 路径不丢字段（run_detectors 注入的字段在内存对象上，
        execute 写 reason_data 时从内存取，绕开 SQL list_signals 回读丢失问题）。
        """
        info = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        info.price = 50000.0
        strategy = make_strategy(exchange, [info])

        actions = await strategy.execute(execution_id="exec042")

        assert len(actions) == 1
        db_actions = exchange.db.list_actions_by_execution("exec042")
        from typing import cast
        snapshot = cast(dict[str, object], db_actions[0].reason_data["market_snapshot"])
        signals_list = cast(list[dict[str, object]], snapshot["signals"])
        assert len(signals_list) >= 1
        meta = cast(dict[str, object], signals_list[0]["metadata"])
        # current_price/time 不应在 signal metadata（移至 market_snapshot 第一层）
        assert "current_price" not in meta, "signals[].metadata 不应含 current_price（冗余）"
        assert "current_time" not in meta, "signals[].metadata 不应含 current_time（冗余）"
        # kline_close_time_str 应在 signal metadata（走 reason_data 路径不丢失）
        assert "kline_close_time_str" in meta, (
            "signals[].metadata 应含 kline_close_time_str（走 reason_data 路径不丢失）"
        )

    @pytest.mark.asyncio
    async def test_market_snapshot_only_contains_best_symbol_signals(
        self, exchange: MockExchange,
    ) -> None:
        """✅ market_snapshot.signals 应只含 best.symbol 的信号，不混入其他 symbol。

        场景：BTCUSDT 和 ETHUSDT 都触发 1d 连续上涨信号，best 选了 BTCUSDT。
        market_snapshot 应只含 BTCUSDT 的信号，不能混入 ETHUSDT。
        聚焦当前生成贴文的 symbol，而非所有候选币大杂烩。
        """
        from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
        btc = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        eth = make_info("ETHUSDT", [(10, 11), (11, 12), (12, 13)])
        repo = exchange.db
        strategy = ContentScanStrategy(
            exchange=exchange,
            config=ContentScanConfig(),
            symbol_picker=FakePicker([btc, eth]),
            signal_detectors=[
                ConsecutiveCandleDetector(repo=repo, client=None, interval="1d", min_streak=3),
            ],
        )

        actions = await strategy.execute(execution_id="exec043")

        assert len(actions) == 1
        best_symbol = actions[0].symbol
        db_actions = exchange.db.list_actions_by_execution("exec043")
        from typing import cast
        snapshot = cast(dict[str, object], db_actions[0].reason_data["market_snapshot"])
        signals_list = cast(list[dict[str, object]], snapshot["signals"])
        # market_snapshot 的 symbol 应与 best 一致
        assert snapshot["symbol"] == best_symbol
        # market_snapshot 应只含 best.symbol 的信号，不混入其他候选币
        # BTC 和 ETH 各产 1 条信号（共 2 条），但 market_snapshot 只应含 best_symbol 的 1 条
        assert len(signals_list) == 1, (
            f"market_snapshot 应只含 best.symbol 的信号（1 条），"
            f"实际含 {len(signals_list)} 条（混入了其他 symbol）"
        )
