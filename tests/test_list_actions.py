"""测试 Repository.list_actions 通用动作查询方法（支持按策略/类型/时间过滤）。

用于 ContentScanStrategy 冷却去重：拉取近 N 小时内某策略的 content 动作，
构建 (symbol, signal_type) 冷却集合。

测试覆盖：
1. 正常路径：按 strategy_name + action_type 过滤
2. 时间过滤：since 参数排除早于该时间的动作
3. 排序：按 created_at 倒序（最新在前）
4. 策略隔离：不同 strategy_name 不互相干扰
5. 类型过滤：不同 action_type 不互相干扰
6. limit 截断
7. 空结果
8. reason_data 反序列化为 dict（冷却指纹可用）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_service.repository.abc import StrategyActionRecord


def make_action(
    *,
    strategy_name: str = "content_scan",
    action_type: str = "content",
    symbol: str = "BTCUSDT",
    signal_type: str = "consecutive_rise",
    created_at: datetime | None = None,
) -> StrategyActionRecord:
    """构造一条动作记录，created_at 默认为当前时间。"""
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    return StrategyActionRecord(
        id=f"act_{strategy_name}_{symbol}_{signal_type}_{created_at.isoformat()}",
        execution_id="exec001",
        strategy_name=strategy_name,
        action_type=action_type,
        symbol=symbol,
        reason_text=f"{symbol} {signal_type}",
        reason_data={"signal_type": signal_type},
        created_at=created_at,
    )


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


class TestListActionsFiltering:
    """过滤逻辑测试。"""

    def test_filter_by_strategy_name(self, repo) -> None:
        """✅ 只返回指定 strategy_name 的动作。"""
        repo.save_action(make_action(strategy_name="content_scan", symbol="BTCUSDT"))
        repo.save_action(make_action(strategy_name="micro_cap", symbol="ETHUSDT"))

        results = repo.list_actions(strategy_name="content_scan")

        assert len(results) == 1
        assert results[0].strategy_name == "content_scan"
        assert results[0].symbol == "BTCUSDT"

    def test_filter_by_action_type(self, repo) -> None:
        """✅ 只返回指定 action_type 的动作。"""
        repo.save_action(make_action(action_type="content", symbol="BTCUSDT"))
        repo.save_action(make_action(action_type="open", symbol="ETHUSDT"))

        results = repo.list_actions(action_type="content")

        assert len(results) == 1
        assert results[0].action_type == "content"
        assert results[0].symbol == "BTCUSDT"

    def test_filter_by_since(self, repo) -> None:
        """✅ since 参数排除早于该时间的动作。"""
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=13)
        recent = now - timedelta(hours=2)

        repo.save_action(make_action(symbol="OLDUSDT", created_at=old))
        repo.save_action(make_action(symbol="NEWUSDT", created_at=recent))

        results = repo.list_actions(since=now - timedelta(hours=12))

        assert len(results) == 1
        assert results[0].symbol == "NEWUSDT", "13h 前的动作应被排除"


class TestListActionsOrdering:
    """排序与截断测试。"""

    def test_ordered_desc_by_created_at(self, repo) -> None:
        """✅ 按 created_at 倒序（最新在前）。"""
        base = datetime.now(timezone.utc)
        repo.save_action(make_action(symbol="OLD", created_at=base - timedelta(hours=3)))
        repo.save_action(make_action(symbol="NEW", created_at=base))
        repo.save_action(make_action(symbol="MID", created_at=base - timedelta(hours=1)))

        results = repo.list_actions()

        symbols = [r.symbol for r in results]
        assert symbols == ["NEW", "MID", "OLD"], f"应倒序，实际 {symbols}"

    def test_limit_truncation(self, repo) -> None:
        """✅ limit 截断返回最新的 N 条。"""
        base = datetime.now(timezone.utc)
        for i in range(5):
            repo.save_action(make_action(symbol=f"S{i}", created_at=base + timedelta(seconds=i)))

        results = repo.list_actions(limit=3)

        assert len(results) == 3
        symbols = [r.symbol for r in results]
        assert symbols == ["S4", "S3", "S2"], "应返回最新 3 条"


class TestListActionsEdgeCases:
    """边界与空值测试。"""

    def test_empty_repo_returns_empty(self, repo) -> None:
        """✅ 空仓库返回空列表。"""
        results = repo.list_actions(strategy_name="content_scan")
        assert results == []

    def test_no_filters_returns_all(self, repo) -> None:
        """✅ 不传过滤条件返回全部（倒序）。"""
        repo.save_action(make_action(symbol="A"))
        repo.save_action(make_action(symbol="B"))

        results = repo.list_actions()

        assert len(results) == 2

    def test_reason_data_deserialized_as_dict(self, repo) -> None:
        """✅ reason_data 应反序列化为 dict，可直接取 signal_type。"""
        repo.save_action(make_action(symbol="BTCUSDT", signal_type="volume_surge"))

        results = repo.list_actions()

        assert len(results) == 1
        assert isinstance(results[0].reason_data, dict)
        assert results[0].reason_data["signal_type"] == "volume_surge"
