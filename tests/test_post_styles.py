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
) -> StrategyActionRecord:
    return StrategyActionRecord(
        id=f"act_content_{symbol}",
        execution_id=execution_id,
        strategy_name="content_scan",
        action_type="content",
        symbol=symbol,
        reason_text=f"{symbol} 连续 3 天上涨",
        reason_data={"signal_type": "consecutive_rise", "direction": "bullish"},
        signal_ids=[signal_id],
    )


def _noop_load_posts(symbol: str) -> list[str]:
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
        """✅ 内容型上下文包含信号信息。"""
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
        assert len(context["signals"]) == 1
        assert context["signals"][0]["signal_type"] == "consecutive_rise"

    def test_build_prompt_has_content_role(self, repo) -> None:
        """✅ 内容型 prompt 使用市场观察者角色。"""
        action = make_content_action()
        style = ContentPostStyle()
        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        prompt = style.build_prompt(context)

        assert "市场观察者" in prompt
        assert "马丁格尔做空" not in prompt
        assert "检测信号" in prompt

    def test_build_context_no_signal_ids(self, repo) -> None:
        """✅ 无 signal_ids 时信号列表为空。"""
        action = make_content_action(signal_id="nonexistent")
        style = ContentPostStyle()

        context = style.build_context(repo, [action], "exec_content_001", _noop_load_posts)

        assert context["signals"] == []


class TestStyleHistoricalPosts:
    """历史贴文传入测试。"""

    def test_load_historical_posts_called(self, repo) -> None:
        """✅ build_context 调用 load_historical_posts 回调。"""
        action = make_trading_action()
        repo.save_action(action)
        style = TradingPostStyle()

        called_symbols: list[str] = []

        def load_posts(symbol: str) -> list[str]:
            called_symbols.append(symbol)
            return ["历史贴文内容"]

        context = style.build_context(repo, [action], "exec001", load_posts)

        assert "BTCUSDT" in called_symbols
        assert context["historical_posts"] == ["历史贴文内容"]
