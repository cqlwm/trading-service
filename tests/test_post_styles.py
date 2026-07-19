"""测试 PostStyle 贴文风格。

验证两种风格的 action_type 匹配、上下文构建产出、prompt 内容差异。
"""
from __future__ import annotations

import pytest

from trading_service.content.styles import ContentPostStyle, TradingPostStyle
from trading_service.repository.abc import StrategyActionRecord


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


def make_trading_action(
    symbol: str = "BTCUSDT",
    action_type: str = "open",
    execution_id: str = "exec001",
) -> StrategyActionRecord:
    return StrategyActionRecord(
        id=f"act_{symbol}_{action_type}",
        execution_id=execution_id,
        strategy_name="martingale_short",
        action_type=action_type,
        symbol=symbol,
        position_id="pos001",
        order_id="ord001",
        reason_text=f"开仓 @ 65000",
        reason_data={"action": "initial_entry", "price": 65000.0},
    )


def make_content_action(
    symbol: str = "BTCUSDT",
    execution_id: str = "exec_content_001",
    signal_id: str = "sig001",
    market_snapshot: dict[str, object] | None = None,
) -> StrategyActionRecord:
    """构造 content 动作。market_snapshot 为 None 时模拟旧数据（无快照，走回退）。"""
    reason_data: dict[str, object] = {
        "signal_type": "consecutive_rise",
        "direction": "bullish",
    }
    if market_snapshot is not None:
        reason_data["market_snapshot"] = market_snapshot
    return StrategyActionRecord(
        id=f"act_content_{symbol}",
        execution_id=execution_id,
        strategy_name="content_scan",
        action_type="content",
        symbol=symbol,
        reason_text=f"{symbol} 连续 3 天上涨",
        reason_data=reason_data,
        signal_ids=[signal_id],
    )


def _make_snapshot(
    symbol: str = "BTCUSDT",
    signals: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """构造典型 market_snapshot。"""
    return {
        "symbol": symbol,
        "current_price": 50000.0,
        "current_time": "2026-07-19T10:00:00+00:00",
        "price_change_pct_24h": 35.0,
        "signals": signals or [
            {"signal_type": "consecutive_rise", "direction": "bullish",
             "severity": 3, "description": "连阳", "interval": "1d",
             "metadata": {"interval": "1d", "current_price": 50000.0}},
        ],
    }


def _noop_load_posts(symbol: str) -> list[dict[str, str]]:
    return []


class TestStyleActionType:
    """action_type 匹配测试。"""

    def test_trading_style_action_type(self) -> None:
        """✅ TradingPostStyle.action_type == 'trading'。"""
        assert TradingPostStyle().action_type == "trading"

    def test_content_style_action_type(self) -> None:
        """✅ ContentPostStyle.action_type == 'content'。"""
        assert ContentPostStyle().action_type == "content"


class TestTradingPostStyle:
    """交易型风格测试。"""

    def test_build_context_includes_story_and_positions(self, repo) -> None:
        """✅ 交易型上下文包含故事线和持仓。"""
        action = make_trading_action(symbol="BTCUSDT")
        repo.save_action(action)
        style = TradingPostStyle()

        context = style.build_context(repo, [action], "exec001", _noop_load_posts)

        assert context["symbol"] == "BTCUSDT"
        assert context["strategy_name"] == "martingale_short"
        assert len(context["current_actions"]) == 1
        assert len(context["full_story"]) >= 1, "应包含完整故事线"
        assert "open_positions" in context

    def test_build_prompt_has_trading_role(self, repo) -> None:
        """✅ 交易型 prompt 使用交易员角色。"""
        action = make_trading_action()
        repo.save_action(action)
        style = TradingPostStyle()
        context = style.build_context(repo, [action], "exec001", _noop_load_posts)

        prompt = style.build_prompt(context)

        assert "马丁格尔做空" in prompt
        assert "市场观察者" not in prompt
        assert "交易故事线" in prompt


class TestContentPostStyle:
    """内容型风格测试。"""

    def test_build_context_includes_signals(self, repo) -> None:
        """✅ 内容型上下文包含信号信息（回退路径：旧数据走 list_signals）。"""
        from trading_service.repository.abc import SignalRecord
        repo.save_signal(SignalRecord(
            id="sig001",
            symbol="BTCUSDT",
            signal_type="consecutive_rise",
            direction="bullish",
            severity=3,
            description="BTCUSDT 连续 3 天上涨",
            metadata_json={"streak_days": 3},
        ))
        action = make_content_action(symbol="BTCUSDT", signal_id="sig001")
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        assert context["symbol"] == "BTCUSDT"
        assert context["strategy_name"] == "content_scan"
        assert len(context["market_snapshot"]["signals"]) == 1  # type: ignore[index]
        assert context["market_snapshot"]["signals"][0]["signal_type"] == "consecutive_rise"  # type: ignore[index]

    def test_build_prompt_has_content_role(self, repo) -> None:
        """✅ 内容型 prompt 使用市场观察者角色。"""
        action = make_content_action()
        style = ContentPostStyle()
        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        prompt = style.build_prompt(context)

        assert "市场观察者" in prompt
        assert "马丁格尔做空" not in prompt
        assert "市场快照" in prompt

    def test_build_context_no_signal_ids(self, repo) -> None:
        """✅ 无 signal_ids 时（旧数据回退）信号列表为空。"""
        action = make_content_action(signal_id="nonexistent")
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        assert context["market_snapshot"]["signals"] == []  # type: ignore[index]

    def test_build_context_uses_market_snapshot(self, repo) -> None:
        """✅ reason_data 含 market_snapshot 时，context 应直接取快照（不走 list_signals）。"""
        snapshot = _make_snapshot(signals=[
            {"signal_type": "breakout_high", "direction": "bullish", "severity": 3,
             "description": "突破", "interval": "1d", "metadata": {"interval": "1d"}},
            {"signal_type": "consecutive_rise", "direction": "bullish", "severity": 3,
             "description": "连阳", "interval": "4h", "metadata": {"interval": "4h"}},
        ])
        # 不预置任何信号到 repo，验证不走 list_signals
        action = make_content_action(symbol="BTCUSDT", market_snapshot=snapshot)
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        assert context["market_snapshot"] == snapshot, (
            "context.market_snapshot 应直接取 reason_data.market_snapshot"
        )
        # 快照里应含 2 条信号
        assert len(context["market_snapshot"]["signals"]) == 2  # type: ignore[index]

    def test_build_context_legacy_falls_back_to_signals(self, repo) -> None:
        """✅ 旧数据无 market_snapshot -> 回退到 list_signals 反查（兼容）。"""
        from trading_service.repository.abc import SignalRecord
        repo.save_signal(SignalRecord(
            id="sig001",
            symbol="BTCUSDT",
            signal_type="consecutive_rise",
            direction="bullish",
            severity=3,
            description="BTCUSDT 连续 3 天上涨",
            metadata_json={"streak_days": 3},
        ))
        # market_snapshot=None 模拟旧数据
        action = make_content_action(symbol="BTCUSDT", signal_id="sig001", market_snapshot=None)
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        # 旧数据回退：market_snapshot 非空（从 list_signals 构建）
        assert context["market_snapshot"] is not None
        assert "signals" in context["market_snapshot"]  # type: ignore[operator]
        assert len(context["market_snapshot"]["signals"]) == 1  # type: ignore[index]
        assert context["market_snapshot"]["signals"][0]["signal_type"] == "consecutive_rise"  # type: ignore[index]

    def test_prompt_includes_market_snapshot(self, repo) -> None:
        """✅ prompt 应含“市场快照”段 + current_price + 所有 signal_type。"""
        snapshot = _make_snapshot(signals=[
            {"signal_type": "breakout_high", "direction": "bullish", "severity": 3,
             "description": "突破", "interval": "1d", "metadata": {"interval": "1d"}},
            {"signal_type": "consecutive_rise", "direction": "bullish", "severity": 3,
             "description": "连阳", "interval": "4h", "metadata": {"interval": "4h"}},
        ])
        action = make_content_action(symbol="BTCUSDT", market_snapshot=snapshot)
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)
        prompt = style.build_prompt(context)

        assert "市场快照" in prompt, "prompt 应含'市场快照'段标题"
        assert "50000" in prompt, "prompt 应含 current_price 值"
        # 两个信号都应出现在 prompt 中（不只 best 1 条）
        assert "breakout_high" in prompt, "prompt 应含 breakout_high 信号"
        assert "consecutive_rise" in prompt, "prompt 应含 consecutive_rise 信号"

    def test_prompt_contains_all_signals_not_only_best(self, repo) -> None:
        """✅ prompt 应含所有信号，而非只有降级链选中的 best。"""
        snapshot = _make_snapshot(signals=[
            {"signal_type": "volume_surge", "direction": "bullish", "severity": 5,
             "description": "放量", "interval": "1d", "metadata": {"interval": "1d"}},
            {"signal_type": "price_surge", "direction": "bullish", "severity": 3,
             "description": "暴涨", "interval": "ticker", "metadata": {"interval": "ticker"}},
        ])
        action = make_content_action(symbol="BTCUSDT", market_snapshot=snapshot)
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)
        prompt = style.build_prompt(context)

        # 两个信号都应在 prompt 中（旧逻辑只有 best 1 条，新逻辑全部进上下文）
        assert "volume_surge" in prompt
        assert "price_surge" in prompt


class TestStyleHistoricalPosts:
    """历史贴文传入测试。"""

    def test_load_historical_posts_called(self, repo) -> None:
        """✅ build_context 调用 load_historical_posts 回调。"""
        action = make_trading_action()
        repo.save_action(action)
        style = TradingPostStyle()

        called_symbols: list[str] = []

        def load_posts(symbol: str) -> list[dict[str, str]]:
            called_symbols.append(symbol)
            return [{"time": "2026-07-13T10:00:00+00:00", "text": "历史贴文内容"}]

        context = style.build_context(repo, [action], "exec001", load_posts)

        assert "BTCUSDT" in called_symbols
        assert context["historical_posts"] == [{"time": "2026-07-13T10:00:00+00:00", "text": "历史贴文内容"}]
