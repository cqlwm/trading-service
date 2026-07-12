"""K 线工具函数：DataFrame 构建 + 按需拉取缓存。

build_ohlcv_dataframe: list[BinanceFutureKline] -> pd.DataFrame，网络层 DTO 到业务层载体的转换边界。
ensure_klines: 按 interval 获取 DataFrame，有缓存则用，有 client 则 lazy-fetch 并缓存，否则返回 None。
"""
from __future__ import annotations

import pandas as pd

from trading_service.clients.binance_client import BinanceFutureKline
from trading_service.clients.protocols import KlineClient
from trading_service.pickers.base import SymbolInfo


def build_ohlcv_dataframe(klines: list[BinanceFutureKline]) -> pd.DataFrame:
    """将 list[BinanceFutureKline] 转为含 OHLCV 列的 DataFrame。

    BinanceFutureKline 到此为止，不再向下传递。
    列：datetime, open, high, low, close, volume。
    """
    return pd.DataFrame({
        "datetime": [k.close_time for k in klines],
        "open": [k.open_price_float for k in klines],
        "high": [k.high_price_float for k in klines],
        "low": [k.low_price_float for k in klines],
        "close": [k.close_price_float for k in klines],
        "volume": [k.volume_float for k in klines],
    })


def ensure_klines(
    info: SymbolInfo,
    interval: str,
    client: KlineClient | None = None,
    limit: int = 210,
) -> pd.DataFrame | None:
    """获取指定 interval 的 klines DataFrame。

    有缓存则直接返回；无缓存但有 client 则拉取、构建、缓存后返回；都没有则返回 None。
    """
    if interval in info.klines:
        return info.klines[interval]
    if client is None:
        return None

    klines = client.get_future_klines(symbol=info.symbol, interval=interval, limit=limit)
    if len(klines) < 2:
        return None

    df = build_ohlcv_dataframe(klines)
    info.klines[interval] = df
    return df
