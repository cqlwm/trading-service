"""阳线过滤器：拉日线 K 线，存入 klines["1d"]，丢弃昨日非阳线代币。

设计为「丢弃式」过滤器：不符合阳线条件的直接移除。
拉取的 K 线数据存入 info.klines["1d"]，后续多时间框架分析可复用，不重新拉取。
"""
from __future__ import annotations

import logging

from trading_service.clients.protocols import KlineClient
from trading_service.pickers.base import SymbolInfo
from trading_service.pickers.kline_utils import ensure_klines
from trading_service.pickers.pipeline import ISymbolFilter

logger = logging.getLogger(__name__)


class BullishKlineFilter(ISymbolFilter):
    """阳线过滤器：拉取指定 interval 的 K 线，丢弃昨日非阳线代币。

    阳线定义：昨日（倒数第二根）收盘价 >= 开盘价。
    拉取的 K 线存入 info.klines[interval]，供后续复用。
    """

    def __init__(self, client: KlineClient, interval: str = "1d", limit: int = 5) -> None:
        self.client = client
        self.interval = interval
        self.limit = limit

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        """过滤出昨日阳线的代币。"""
        import asyncio
        loop = asyncio.get_event_loop()

        result: list[SymbolInfo] = []
        for info in infos:
            kept = await loop.run_in_executor(None, self._check_bullish, info)
            if kept:
                result.append(info)

        logger.info(f"阳线过滤: {len(infos)} -> {len(result)} (interval={self.interval})")
        return result

    def _check_bullish(self, info: SymbolInfo) -> bool:
        """拉取 K 线，存入 klines，判定昨日是否阳线。"""
        df = ensure_klines(info, self.interval, self.client, self.limit)
        if df is None or len(df) < 2:
            return False

        yesterday = df.iloc[-2]
        return float(yesterday["close"]) >= float(yesterday["open"])
