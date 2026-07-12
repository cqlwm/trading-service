"""测试 TechnicalAnalyzer 技术分析工具。

基于 DataFrame 的信号判定测试。
覆盖 detect_200sma_signal 的正常路径、边界条件、优先级、空值/零值等场景。
"""
from __future__ import annotations

import pandas as pd
import pytest

from trading_service.pickers.technical_analyzer import (
    CrossSignal,
    ITechnicalAnalyzer,
    TechnicalAnalyzer,
)
from trading_service.types import CrossSignalType


def make_kline_row(
    open_price: float, high: float, low: float, close: float, volume: float = 100.0
) -> dict:
    """构造一行 K 线数据。"""
    return {
        "datetime": 0,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def make_flat_df(count: int, price: float = 100.0) -> pd.DataFrame:
    """构造 count 根价格恒定为 price 的 K 线 DataFrame。"""
    return pd.DataFrame([make_kline_row(price, price, price, price) for _ in range(count)])


class TestDetect200smaSignalInsufficientData:
    """测试 detect_200sma_signal 数据不足场景。"""

    def test_returns_none_when_less_than_201_klines(self) -> None:
        """边界：K 线数 < 201 时返回 None。"""
        df = make_flat_df(200, 100.0)
        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is None, "K线不足201根应返回 None"

    def test_works_with_exactly_201_klines(self) -> None:
        """边界：刚好 201 根 K 线时应能计算（不返回 None 因数据不足）。"""
        df = make_flat_df(201, 100.0)
        # 价格恒定，刚好在均线上（distance=0 <= near_threshold），应返回 near 信号
        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None, "201根恒定价格K线应返回 near 信号"


class TestDetect200smaGoldenCross:
    """测试 detect_200sma_signal 金叉检测。"""

    def test_detect_golden_cross(self) -> None:
        """正常路径：收盘价从下向上穿越 SMA200，返回 golden 信号。"""
        # 200 根低价 K 线形成 SMA=50，随后价格上穿
        rows = [make_kline_row(50, 50, 50, 50) for _ in range(200)]
        # 第 201 根：价格仍低于均线附近
        rows.append(make_kline_row(50, 50, 50, 50))
        # 第 202 根：价格突破均线（金叉）
        rows.append(make_kline_row(48, 70, 48, 70))
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None, "金叉应返回信号"
        assert result.cross_type == CrossSignalType.GOLDEN, f"信号类型应为 golden，实际 {result.cross_type}"
        assert result.cross_ago >= 0

    def test_detect_dead_cross(self) -> None:
        """正常路径：收盘价从上向下穿越 SMA200，返回 dead 信号。"""
        # 200 根高价 K 线形成 SMA=100
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(200)]
        rows.append(make_kline_row(100, 100, 100, 100))
        # 价格跌破均线（死叉）
        rows.append(make_kline_row(102, 102, 80, 80))
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        assert result.cross_type == CrossSignalType.DEAD, f"信号类型应为 dead，实际 {result.cross_type}"


class TestDetect200smaNearAndPriority:
    """测试靠近均线检测与优先级。"""

    def test_detect_near_when_close_to_sma(self) -> None:
        """正常路径：无穿越但价格靠近均线（距离<=5%），返回 near 信号。"""
        # 200 根形成 SMA=100，随后 15 根价格稳定在 103（均线上方，无穿越）
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(200)]
        rows.extend([make_kline_row(103, 103, 103, 103) for _ in range(15)])
        # 最后一根微调到 102（距离均线约 2% <= 5%，无穿越）
        rows[-1] = make_kline_row(103, 103, 102, 102)
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        assert result.cross_type == CrossSignalType.NEAR, f"应返回 near，实际 {result.cross_type}"

    def test_returns_none_when_far_from_sma_no_cross(self) -> None:
        """正常路径：无穿越且远离均线（距离>5%），返回 None。"""
        # 价格长期稳定在 120（远高于均线 100），扫描窗口内无穿越
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(200)]
        rows.extend([make_kline_row(120, 120, 120, 120) for _ in range(15)])
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is None, "远离均线且无穿越应返回 None"

    def test_golden_cross_takes_priority_over_near(self) -> None:
        """优先级：金叉与靠近同时满足时，优先返回 golden（穿越优先）。"""
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(200)]
        rows.append(make_kline_row(100, 100, 100, 100))
        # 价格从均线下方上穿，且穿越后距离小（同时满足金叉和靠近）
        rows.append(make_kline_row(98, 103, 98, 103))
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        assert result.cross_type == CrossSignalType.GOLDEN, "金叉应优先于 near"


class TestDetect200smaVolatilityAndSideways:
    """测试波动率计算与横盘判定。"""

    def test_signal_contains_volatility(self) -> None:
        """正常路径：返回的信号包含最近10根K线波动率。"""
        df = make_flat_df(210, 100.0)
        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        # 恒定价格，high=low，波动率应为 0
        assert result.volatility_10 == 0.0

    def test_volatility_calculation_with_range(self) -> None:
        """正常路径：波动率 = (high-low)/low*100。"""
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(200)]
        rows.append(make_kline_row(100, 100, 100, 100))
        # 最后加入几根有高低差的 K 线，使最近10根 high=120, low=90
        for _ in range(9):
            rows.append(make_kline_row(100, 120, 90, 105))
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        # (120-90)/90*100 = 33.33...
        assert abs(result.volatility_10 - 33.333333) < 0.01

    def test_sideways_detected_when_low_volatility_above_sma(self) -> None:
        """正常路径：低波动率 + 价格在均线上方 + 距离<=15%，判定为横盘。"""
        rows = [make_kline_row(100, 100, 100, 100) for _ in range(210)]
        # 恒定价格，波动率 0 <= 20%，价格=均线（distance=0 <=15），但需 price > sma
        # 微调最后价格略高于均线
        rows[-1] = make_kline_row(100, 101, 100, 101)
        df = pd.DataFrame(rows)

        result = TechnicalAnalyzer().detect_200sma_signal(df, "BTCUSDT")
        assert result is not None
        assert result.is_sideways is True, "低波动+均线上方应判定横盘"


class TestCrossSignalDataclass:
    """测试 CrossSignal 数据结构。"""

    def test_cross_signal_fields(self) -> None:
        """正常路径：CrossSignal 包含所有必要字段。"""
        signal = CrossSignal(
            symbol="BTCUSDT",
            cross_type=CrossSignalType.GOLDEN,
            cross_ago=0,
            current_price=100.0,
            sma_200=95.0,
            distance_percent=5.26,
            volatility_10=2.0,
            is_sideways=False,
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.cross_type == CrossSignalType.GOLDEN
        assert signal.is_sideways is False


class TestITechnicalAnalyzerInterface:
    """测试 ITechnicalAnalyzer 接口契约。"""

    def test_technical_analyzer_implements_interface(self) -> None:
        """隔离：TechnicalAnalyzer 必须实现 ITechnicalAnalyzer 接口。"""
        analyzer: ITechnicalAnalyzer = TechnicalAnalyzer()
        assert isinstance(analyzer, ITechnicalAnalyzer)

    def test_interface_has_detect_200sma_signal(self) -> None:
        """正常路径：ITechnicalAnalyzer 接口必须定义 detect_200sma_signal 方法。"""
        assert hasattr(ITechnicalAnalyzer, "detect_200sma_signal"), \
            "ITechnicalAnalyzer 必须定义 detect_200sma_signal 抽象方法"

    def test_interface_is_abstract(self) -> None:
        """边界：ITechnicalAnalyzer 是抽象基类，不能直接实例化。"""
        with pytest.raises(TypeError):
            ITechnicalAnalyzer()  # type: ignore[abstract]
