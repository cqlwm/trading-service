"""涨幅榜数据源：从币安合约 24h 行情中选取涨幅最大的交易对。"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from trading_service.clients import BinanceClient
from trading_service.pickers.base import SymbolInfo
from trading_service.pickers.pipeline import ISymbolSource

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=1)


class TopGainersSource(ISymbolSource):
    """24 小时涨幅榜数据源。

    从币安合约获取所有 USDT 永续的 24h ticker，
    按 price_change_percent 降序取 Top N，返回 SymbolInfo 列表。
    """

    def __init__(
        self,
        client: BinanceClient,
        top_n: int = 20,
        min_quote_volume: float = 10_000_000,
    ) -> None:
        self._client = client
        self._top_n = top_n
        self._min_quote_volume = min_quote_volume

    async def fetch(self) -> list[SymbolInfo]:
        """获取涨幅榜 Top N。"""
        # BinanceClient 是同步的，用线程池包装避免阻塞事件循环
        return await asyncio.get_event_loop().run_in_executor(
            _EXECUTOR, self._fetch_sync
        )

    def _fetch_sync(self) -> list[SymbolInfo]:
        """同步获取涨幅榜（在线程池中执行）。"""
        tickers = self._client.get_future_ticker_24hr()
        logger.info(f"获取到 {len(tickers)} 个合约 24h 行情")

        # 过滤：USDT 结尾 + 成交量达标
        candidates = [
            t for t in tickers
            if t.symbol.endswith("USDT")
            and float(t.quote_volume) >= self._min_quote_volume
        ]

        # 按涨幅降序排序取 Top N
        candidates.sort(key=lambda t: t.price_change_percent_float, reverse=True)
        top = candidates[: self._top_n]

        result = [
            SymbolInfo(
                symbol=t.symbol,
                price=t.last_price_float,
                volume_24h=float(t.quote_volume),
                price_change_pct_24h=t.price_change_percent_float,
            )
            for t in top
        ]

        logger.info(
            f"涨幅榜 Top {len(result)}: "
            + ", ".join(f"{r.symbol}({r.price_change_pct_24h:.1f}%)" for r in result[:5])
        )
        return result
