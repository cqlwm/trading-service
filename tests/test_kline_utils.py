"""测试 K 线工具函数：build_ohlcv_dataframe 的未收盘 K 线截断。

关键不变量：build_ohlcv_dataframe 丢弃最后一根 close_time 在未来的 K 线（未收盘），
保留所有已收盘 K 线。这是防止信号闪烁的源头防线。
"""
from __future__ import annotations

from datetime import datetime, timezone

from trading_service.clients.binance_client import BinanceFutureKline
from trading_service.pickers.kline_utils import build_ohlcv_dataframe


def _make_kline(
    open_p: float = 100.0,
    close_p: float = 100.0,
    close_time: int = 0,
) -> BinanceFutureKline:
    """构造一根 K 线，close_time 可指定（0=过去/已收盘）。"""
    high = max(open_p, close_p)
    low = min(open_p, close_p)
    return BinanceFutureKline(
        open_time=0, open_price=str(open_p), high_price=str(high),
        low_price=str(low), close_price=str(close_p), volume="100",
        close_time=close_time, quote_volume="0", trade_count=0,
        taker_buy_base_volume="0", taker_buy_quote_volume="0", ignore="0",
    )


def _future_ms(offset_seconds: int = 3600) -> int:
    """返回未来的毫秒时间戳。"""
    now = datetime.now(timezone.utc)
    return int(now.timestamp() * 1000) + offset_seconds * 1000


def _past_ms(offset_seconds: int = 3600) -> int:
    """返回过去的毫秒时间戳。"""
    now = datetime.now(timezone.utc)
    return int(now.timestamp() * 1000) - offset_seconds * 1000


class TestBuildOhlcvDataframeColumns:
    """DataFrame 列结构测试。"""

    def test_columns_present(self) -> None:
        """✅ DataFrame 包含 datetime/open/high/low/close/volume 列。"""
        klines = [_make_kline(100, 110), _make_kline(110, 105)]
        df = build_ohlcv_dataframe(klines)

        assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
        assert len(df) == 2


class TestUnclosedKlineDropped:
    """未收盘 K 线截断测试。"""

    def test_drops_last_unclosed_kline(self) -> None:
        """✅ 最后一根 close_time 在未来 -> 被丢弃，行数 = N-1。"""
        klines = [
            _make_kline(100, 110, close_time=_past_ms(7200)),
            _make_kline(110, 105, close_time=_past_ms(3600)),
            _make_kline(105, 108, close_time=_future_ms(3600)),  # 未收盘
        ]
        df = build_ohlcv_dataframe(klines)

        assert len(df) == 2, f"应丢弃最后 1 根未收盘 K 线，实际行数 {len(df)}"
        # 最后一行应是第二根（已收盘），close=105
        assert float(df.iloc[-1]["close"]) == 105.0

    def test_keeps_last_closed_kline(self) -> None:
        """✅ 最后一根 close_time 在过去 -> 保留，行数 = N。"""
        klines = [
            _make_kline(100, 110, close_time=_past_ms(7200)),
            _make_kline(110, 105, close_time=_past_ms(3600)),
        ]
        df = build_ohlcv_dataframe(klines)

        assert len(df) == 2, f"全部已收盘应全部保留，实际行数 {len(df)}"

    def test_all_closed_klines_kept(self) -> None:
        """✅ 全部已收盘（close_time=0）-> 全部保留。"""
        klines = [_make_kline(100, 110), _make_kline(110, 105), _make_kline(105, 108)]
        df = build_ohlcv_dataframe(klines)

        assert len(df) == 3

    def test_empty_klines_returns_empty_dataframe(self) -> None:
        """✅ 空列表 -> 返回空 DataFrame（不崩溃）。"""
        df = build_ohlcv_dataframe([])

        assert len(df) == 0
        assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]

    def test_single_unclosed_kline_returns_empty(self) -> None:
        """✅ 只有一根未收盘 K 线 -> 截断后返回空 DataFrame（不崩溃）。"""
        klines = [_make_kline(100, 110, close_time=_future_ms(3600))]
        df = build_ohlcv_dataframe(klines)

        assert len(df) == 0, "唯一一根未收盘 K 线应被截断，结果为空"

    def test_only_drops_last_one(self) -> None:
        """✅ 只截断最后一根，中间不会误删。"""
        # 第一根未收盘但不是最后一根 -> 不应被截断（实际不会出现，但验证逻辑只看最后一根）
        klines = [
            _make_kline(100, 110, close_time=_future_ms(7200)),  # 未来但非最后
            _make_kline(110, 105, close_time=_past_ms(3600)),    # 过去，最后一根
        ]
        df = build_ohlcv_dataframe(klines)

        assert len(df) == 2, "只检查最后一根的 close_time，中间的不管"
