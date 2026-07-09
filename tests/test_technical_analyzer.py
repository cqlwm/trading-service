"""测试 TechnicalAnalyzer 技术分析工具。

TDD 红阶段：覆盖 calculate_sma / detect_200sma_signal / is_bottom_sideways 的
正常路径、边界条件、优先级、空值/零值等场景。
使用内存构造的 BinanceFutureKline 列表，不调用真实 API。
"""
from __future__ import annotations

import pytest

from trading_service.clients import BinanceFutureKline
from trading_service.pickers.technical_analyzer import (
    CrossSignal,
    ITechnicalAnalyzer,
    TechnicalAnalyzer,
)


def make_kline(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: str = "100",
) -> BinanceFutureKline:
    """构造一根内存 K 线，避免调用真实 API。"""
    return BinanceFutureKline(
        open_time=0,
        open_price=str(open_price),
        high_price=str(high),
        low_price=str(low),
        close_price=str(close),
        volume=volume,
        close_time=0,
        quote_volume="0",
        trade_count=0,
        taker_buy_base_volume="0",
        taker_buy_quote_volume="0",
        ignore="0",
    )


def make_flat_klines(count: int, price: float = 100.0) -> list[BinanceFutureKline]:
    """构造 count 根价格恒定为 price 的 K 线（用于 SMA 测试）。"""
    return [make_kline(price, price, price, price) for _ in range(count)]


class TestCalculateSma:
    """测试 SMA 简单移动平均线计算。"""

    def test_sma_basic_calculation(self) -> None:
        """正常路径：period=3 的 SMA 计算正确。"""
        klines = [
            make_kline(10, 10, 10, 10),
            make_kline(20, 20, 20, 20),
            make_kline(30, 30, 30, 30),
        ]
        sma = TechnicalAnalyzer.calculate_sma(klines, period=3)
        # 前 period-1=2 个为 None，第 3 个为 (10+20+30)/3 = 20
        assert sma[0] is None
        assert sma[1] is None
        assert sma[2] == 20.0

    def test_sma_insufficient_data_all_none(self) -> None:
        """边界：数据量不足 period 时全部返回 None。"""
        klines = make_flat_klines(2, 100.0)
        sma = TechnicalAnalyzer.calculate_sma(klines, period=5)
        assert all(v is None for v in sma)

    def test_sma_empty_klines(self) -> None:
        """空值/零值：空 K 线列表返回空列表。"""
        sma = TechnicalAnalyzer.calculate_sma([], period=10)
        assert sma == []

    def test_sma_period_one(self) -> None:
        """边界：period=1 时每个点等于自身收盘价。"""
        klines = [
            make_kline(0, 0, 0, 5),
            make_kline(0, 0, 0, 15),
        ]
        sma = TechnicalAnalyzer.calculate_sma(klines, period=1)
        assert sma == [5.0, 15.0]


class TestDetect200smaSignalInsufficientData:
    """测试 detect_200sma_signal 数据不足场景。"""

    def test_returns_none_when_less_than_201_klines(self) -> None:
        """边界：K 线数 < 201 时返回 None。"""
        klines = make_flat_klines(200, 100.0)
        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is None, "K线不足201根应返回 None"

    def test_works_with_exactly_201_klines(self) -> None:
        """边界：刚好 201 根 K 线时应能计算（不返回 None 因数据不足）。"""
        klines = make_flat_klines(201, 100.0)
        # 价格恒定，刚好在均线上（distance=0 <= near_threshold），应返回 near 信号
        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None, "201根恒定价格K线应返回 near 信号"


class TestDetect200smaGoldenCross:
    """测试 detect_200sma_signal 金叉检测。"""

    def test_detect_golden_cross(self) -> None:
        """正常路径：收盘价从下向上穿越 SMA200，返回 golden 信号。"""
        # 200 根低价 K 线形成 SMA=50，随后价格上穿
        klines = make_flat_klines(200, 50.0)
        # 第 201 根：价格仍低于均线附近
        klines.append(make_kline(50, 50, 50, 50))
        # 第 202 根：价格突破均线（金叉）
        klines.append(make_kline(48, 70, 48, 70))

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None, "金叉应返回信号"
        assert result.cross_type == "golden", f"信号类型应为 golden，实际 {result.cross_type}"
        assert result.cross_ago >= 0

    def test_detect_dead_cross(self) -> None:
        """正常路径：收盘价从上向下穿越 SMA200，返回 dead 信号。"""
        # 200 根高价 K 线形成 SMA=100
        klines = make_flat_klines(200, 100.0)
        klines.append(make_kline(100, 100, 100, 100))
        # 价格跌破均线（死叉）
        klines.append(make_kline(102, 102, 80, 80))

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        assert result.cross_type == "dead", f"信号类型应为 dead，实际 {result.cross_type}"


class TestDetect200smaNearAndPriority:
    """测试靠近均线检测与优先级。"""

    def test_detect_near_when_close_to_sma(self) -> None:
        """正常路径：无穿越但价格靠近均线（距离<=5%），返回 near 信号。"""
        # 构造无穿越的靠近场景：价格长期在均线上方，最后小幅靠近均线
        # 200 根形成 SMA=100，随后 15 根价格稳定在 103（均线上方，无穿越）
        klines = make_flat_klines(200, 100.0)
        klines.extend(make_flat_klines(15, 103.0))
        # 最后一根微调到 102（距离均线约 2% <= 5%，无穿越）
        klines[-1] = make_kline(103, 103, 102, 102)

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        assert result.cross_type == "near", f"应返回 near，实际 {result.cross_type}"

    def test_returns_none_when_far_from_sma_no_cross(self) -> None:
        """正常路径：无穿越且远离均线（距离>5%），返回 None。"""
        # 价格长期稳定在 120（远高于均线 100），扫描窗口内无穿越
        klines = make_flat_klines(200, 100.0)
        klines.extend(make_flat_klines(15, 120.0))

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is None, "远离均线且无穿越应返回 None"

    def test_golden_cross_takes_priority_over_near(self) -> None:
        """优先级：金叉与靠近同时满足时，优先返回 golden（穿越优先）。"""
        klines = make_flat_klines(200, 100.0)
        klines.append(make_kline(100, 100, 100, 100))
        # 价格从均线下方上穿，且穿越后距离小（同时满足金叉和靠近）
        klines.append(make_kline(98, 103, 98, 103))

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        assert result.cross_type == "golden", "金叉应优先于 near"


class TestDetect200smaVolatilityAndSideways:
    """测试波动率计算与横盘判定。"""

    def test_signal_contains_volatility(self) -> None:
        """正常路径：返回的信号包含最近10根K线波动率。"""
        klines = make_flat_klines(210, 100.0)
        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        # 恒定价格，high=low，波动率应为 0
        assert result.volatility_10 == 0.0

    def test_volatility_calculation_with_range(self) -> None:
        """正常路径：波动率 = (high-low)/low*100。"""
        klines = make_flat_klines(200, 100.0)
        klines.append(make_kline(100, 100, 100, 100))
        # 最后加入几根有高低差的 K 线，使最近10根 high=120, low=90
        for _ in range(9):
            klines.append(make_kline(100, 120, 90, 105))

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        # (120-90)/90*100 = 33.33...
        assert abs(result.volatility_10 - 33.333333) < 0.01

    def test_sideways_detected_when_low_volatility_above_sma(self) -> None:
        """正常路径：低波动率 + 价格在均线上方 + 距离<=15%，判定为横盘。"""
        klines = make_flat_klines(210, 100.0)
        # 恒定价格，波动率 0 <= 20%，价格=均线（distance=0 <=15），但需 price > sma
        # 微调最后价格略高于均线
        klines[-1] = make_kline(100, 101, 100, 101)

        result = TechnicalAnalyzer().detect_200sma_signal(klines, "BTCUSDT")
        assert result is not None
        assert result.is_sideways is True, "低波动+均线上方应判定横盘"


class TestIsBottomSideways:
    """测试 is_bottom_sideways 独立横盘判定。"""

    def test_sideways_with_low_volatility(self) -> None:
        """正常路径：波动率低于阈值判定为横盘。"""
        klines = make_flat_klines(30, 100.0)
        assert TechnicalAnalyzer.is_bottom_sideways(klines, period=30, volatility_threshold=25.0) is True

    def test_not_sideways_with_high_volatility(self) -> None:
        """正常路径：波动率高于阈值不判定为横盘。"""
        klines = [make_kline(100, 200, 50, 100) for _ in range(30)]
        # (200-50)/50*100 = 300% >> 25%
        assert TechnicalAnalyzer.is_bottom_sideways(klines, period=30, volatility_threshold=25.0) is False

    def test_returns_false_when_insufficient_data(self) -> None:
        """边界：K 线数不足 period 时返回 False。"""
        klines = make_flat_klines(10, 100.0)
        assert TechnicalAnalyzer.is_bottom_sideways(klines, period=30) is False


class TestCrossSignalDataclass:
    """测试 CrossSignal 数据结构。"""

    def test_cross_signal_fields(self) -> None:
        """正常路径：CrossSignal 包含所有必要字段。"""
        signal = CrossSignal(
            symbol="BTCUSDT",
            cross_type="golden",
            cross_ago=0,
            current_price=100.0,
            sma_200=95.0,
            distance_percent=5.26,
            volatility_10=2.0,
            is_sideways=False,
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.cross_type == "golden"
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
