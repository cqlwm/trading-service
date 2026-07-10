"""测试 is_notable_signal（TDD 红阶段）。

判定是否为值得关注的技术信号：金叉 / 靠近均线 / 底部横盘。
死叉(DEAD)与无信号(None)返回 False。

纯函数测试：覆盖正常路径、边界（死叉）、空值（None/默认值）、组合、幂等。
"""
from __future__ import annotations

from trading_service.pickers import SymbolInfo, is_notable_signal
from trading_service.types import CrossSignalType


def make_info(
    cross_signal: CrossSignalType | None = None,
    is_sideways_bottom: bool = False,
) -> SymbolInfo:
    """构造带技术字段的 SymbolInfo。"""
    info = SymbolInfo(symbol="TESTUSDT")
    info.cross_signal = cross_signal
    info.is_sideways_bottom = is_sideways_bottom
    return info


class TestNotableSignalPositive:
    """正常路径：三类信号返回 True。"""

    def test_golden_returns_true(self) -> None:
        """✅ 金叉信号应关注。"""
        info = make_info(cross_signal=CrossSignalType.GOLDEN)
        assert is_notable_signal(info) is True, "金叉应返回 True"

    def test_near_returns_true(self) -> None:
        """✅ 靠近均线信号应关注。"""
        info = make_info(cross_signal=CrossSignalType.NEAR)
        assert is_notable_signal(info) is True, "靠近均线应返回 True"

    def test_sideways_only_returns_true(self) -> None:
        """✅ 仅底部横盘（无穿越信号）应关注。"""
        info = make_info(cross_signal=None, is_sideways_bottom=True)
        assert is_notable_signal(info) is True, "底部横盘应返回 True"


class TestNotableSignalNegative:
    """边界/空值：不应关注的信号返回 False。"""

    def test_dead_returns_false(self) -> None:
        """❌ 死叉不应关注（关键边界）。"""
        info = make_info(cross_signal=CrossSignalType.DEAD)
        assert is_notable_signal(info) is False, "死叉应返回 False"

    def test_no_signal_returns_false(self) -> None:
        """❌ 无穿越信号且非横盘应返回 False。"""
        info = make_info(cross_signal=None, is_sideways_bottom=False)
        assert is_notable_signal(info) is False, "无信号应返回 False"

    def test_defaults_returns_false(self) -> None:
        """❌ 全新 SymbolInfo 默认值应返回 False。"""
        info = SymbolInfo(symbol="TESTUSDT")
        assert is_notable_signal(info) is False, "默认值应返回 False"


class TestNotableSignalCombination:
    """组合逻辑。"""

    def test_golden_and_sideways_returns_true(self) -> None:
        """组合：金叉 + 横盘同时存在仍返回 True。"""
        info = make_info(
            cross_signal=CrossSignalType.GOLDEN, is_sideways_bottom=True,
        )
        assert is_notable_signal(info) is True

    def test_dead_and_sideways_returns_true(self) -> None:
        """组合：死叉但底部横盘 -> 横盘优先，返回 True。"""
        info = make_info(
            cross_signal=CrossSignalType.DEAD, is_sideways_bottom=True,
        )
        assert is_notable_signal(info) is True, "底部横盘优先于死叉"


class TestNotableSignalIdempotency:
    """幂等性：多次调用结果一致。"""

    def test_idempotent_multiple_calls(self) -> None:
        """幂等性：同一输入多次调用结果一致。"""
        info = make_info(cross_signal=CrossSignalType.GOLDEN)
        results = [is_notable_signal(info) for _ in range(3)]
        assert results == [True, True, True]
