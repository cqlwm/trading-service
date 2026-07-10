"""测试 is_delisting_soon（TDD 红阶段）。

永续合约下架预警：exchangeInfo 中 deliveryDate 偏离哨兵值即为即将下架。
- 哨兵值 4133404800000（2100-12-25）= 正常永续，永不到期
- 具体时点（如 IPUSDT 下架案例 1782637200000）= 即将下架，提前约 15 天预警

验证依据：IPUSDT 永续合约实际下架案例，deliveryDate 从哨兵值变为具体时点。
"""
from __future__ import annotations

from trading_service.pickers import SymbolInfo, is_delisting_soon
from trading_service.pickers.symbol_picker import PERPETUAL_DELIVERY_SENTINEL


def make_info(delivery_date: int | None = None) -> SymbolInfo:
    """构造带 delivery_date 的 SymbolInfo。"""
    info = SymbolInfo(symbol="TESTUSDT")
    info.delivery_date = delivery_date
    return info


class TestDelistingDetection:
    """下架预警判定。"""

    def test_sentinel_not_delisting(self) -> None:
        """✅ 哨兵值（正常永续）-> 不下架。"""
        info = make_info(delivery_date=PERPETUAL_DELIVERY_SENTINEL)
        assert is_delisting_soon(info) is False, "哨兵值应为正常永续，不下架"

    def test_concrete_date_delisting(self) -> None:
        """✅ 具体下架时点（IPUSDT 式）-> 即将下架。"""
        # IPUSDT 实际下架时点：2026-06-28 09:00 UTC
        info = make_info(delivery_date=1782637200000)
        assert is_delisting_soon(info) is True, "具体时点应判定为即将下架"

    def test_none_delivery_not_delisting(self) -> None:
        """空值：delivery_date=None -> 不下架（未知，不报警）。"""
        info = make_info(delivery_date=None)
        assert is_delisting_soon(info) is False, "None 应视为未知，不下架"

    def test_past_date_still_delisting(self) -> None:
        """边界：已过期下架时点仍 True（下架流程中，status 可能已转 SETTLING）。"""
        info = make_info(delivery_date=1000)  # 很早的时点
        assert is_delisting_soon(info) is True, "偏离哨兵值即视为下架流程相关"

    def test_defaults_not_delisting(self) -> None:
        """空值：全新 SymbolInfo 默认 delivery_date=None -> 不下架。"""
        info = SymbolInfo(symbol="TESTUSDT")
        assert is_delisting_soon(info) is False


class TestDelistingIdempotency:
    """幂等性。"""

    def test_idempotent_multiple_calls(self) -> None:
        """幂等性：同一输入多次调用结果一致。"""
        info = make_info(delivery_date=1782637200000)
        results = [is_delisting_soon(info) for _ in range(3)]
        assert results == [True, True, True]


class TestSentinelValue:
    """哨兵常量正确性。"""

    def test_sentinel_is_2100_12_25(self) -> None:
        """哨兵值 = 4133404800000（2100-12-25，永续合约标准哨兵值）。"""
        assert PERPETUAL_DELIVERY_SENTINEL == 4133404800000
