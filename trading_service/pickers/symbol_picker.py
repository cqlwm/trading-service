from __future__ import annotations

import logging

from trading_service.clients import BinanceClient
from trading_service.clients.protocols import AlphaUniverseClient
from trading_service.pickers.base import SymbolInfo  # noqa: F401  (re-export 兼容旧导入路径)
from trading_service.pickers.pipeline import ISymbolSource

logger = logging.getLogger(__name__)

# SymbolInfo / ISymbolPicker / StaticListSymbolPicker 已迁移至 base.py，
# 此处 re-export SymbolInfo 仅保持向后兼容导入路径。
# AlphaTokenSource 是数据源实现，依赖 pipeline.ISymbolSource。

# 永续合约的「永不到期」哨兵值。即将下架时 Binance 会将其改为具体下架时点（ms），
# 据此可提前约 15 天预警下架（见 IPUSDT 永续合约下架案例）。
PERPETUAL_DELIVERY_SENTINEL = 4133404800000  # 2100-12-25 08:00 UTC


class AlphaTokenSource(ISymbolSource):
    """Alpha 代币数据源：只做候选集构建，不做技术分析或交易筛选。

    职责：
    1. 获取 Alpha 代币，市值 5000 万 USDT 以下
    2. 在合约交易所存在且处于可交易状态

    不拉 K 线、不做阳线过滤 -- 交易筛选由独立的 ISymbolFilter 完成。
    """

    MARKET_CAP_THRESHOLD = 50_000_000.0  # 5000 万 USDT

    def __init__(self, client: AlphaUniverseClient | None = None) -> None:
        self.client: AlphaUniverseClient = client or BinanceClient(timeout=30)

    async def fetch(self) -> list[SymbolInfo]:
        """筛选符合条件的代币（async 接口）。"""
        # 同步IO用线程池包装，兼容async框架
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[SymbolInfo]:
        """构建候选代币列表（同步实现）。"""
        logger.info("开始筛选 Alpha 代币...")

        candidate_symbols = self._get_base_candidates()
        if not candidate_symbols:
            return []

        result = [
            SymbolInfo(
                symbol=symbol,
                base_asset=symbol.replace("USDT", ""),
                market_cap=market_cap,
                delivery_date=delivery_date,
            )
            for symbol, (market_cap, delivery_date) in candidate_symbols.items()
        ]

        # 按市值排序（从小到大）
        result.sort(key=lambda x: x.market_cap)
        logger.info(f"最终筛选结果: 共 {len(result)} 个代币符合条件")
        return result

    def _get_base_candidates(self) -> dict[str, tuple[float, int]]:
        """获取基础候选池：Alpha代币 + 5000万以下 + 合约可交易。

        Returns:
            dict[symbol -> (market_cap, delivery_date)]
        """
        # 1. 获取 Alpha 代币列表并按市值过滤
        alpha_tokens = self._get_alpha_tokens_below_cap()
        logger.info(f"Step 1: 获取到 {len(alpha_tokens)} 个市值 5000 万以下的 Alpha 代币")

        if not alpha_tokens:
            logger.warning("没有找到符合市值条件的 Alpha 代币")
            return {}

        # 2. 获取交易所可交易的合约符号（含下架时点 delivery_date）
        tradable_symbols = self._get_tradable_symbols()
        logger.info(f"Step 2: 交易所共有 {len(tradable_symbols)} 个可交易合约对")

        # 3. 取交集（Alpha 代币中可合约交易的）
        candidate_symbols: dict[str, tuple[float, int]] = {}
        for base_asset, market_cap in alpha_tokens.items():
            contract_symbol = f"{base_asset}USDT"
            if contract_symbol in tradable_symbols:
                delivery_date = tradable_symbols[contract_symbol]
                candidate_symbols[contract_symbol] = (market_cap, delivery_date)

        logger.info(f"Step 3: Alpha 代币与可交易合约的交集: {len(candidate_symbols)} 个")
        return candidate_symbols

    def _get_alpha_tokens_below_cap(self) -> dict[str, float]:
        """获取市值 5000 万以下的 Alpha 代币。"""
        tokens = self.client.get_alpha_tokens()
        result: dict[str, float] = {}

        for token in tokens:
            if token.market_cap is not None and token.market_cap < self.MARKET_CAP_THRESHOLD:
                base_asset = token.symbol.strip().upper()
                result[base_asset] = token.market_cap

        return result

    def _get_tradable_symbols(self) -> dict[str, int]:
        """获取交易所所有可交易合约符号及其下架时点。

        Returns:
            dict[symbol -> delivery_date]：delivery_date 为永续哨兵值表示正常，
            偏离哨兵值表示即将下架（见 is_delisting_soon）。
        """
        exchange_info = self.client.get_future_exchange_info()
        tradable: dict[str, int] = {}

        for symbol_info in exchange_info.symbols:
            if (
                symbol_info.status == "TRADING"
                and symbol_info.quote_asset == "USDT"
            ):
                tradable[symbol_info.symbol] = symbol_info.delivery_date

        return tradable
