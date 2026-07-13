from __future__ import annotations

import logging

from trading_service.clients import BinanceClient
from trading_service.clients.binance_client import BinanceAlphaToken
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

        市值口径：circulating_supply × 合约最新价（last_price）。
        circulating_supply 缺失或合约价缺失时，降级用现货 marketCap 兜底。

        Returns:
            dict[symbol -> (market_cap, delivery_date)]
        """
        # 1. 收集 Alpha 代币（不在这一步过滤市值，合约价未知）
        alpha_tokens = self._collect_alpha_tokens()
        logger.info(f"Step 1: 收集到 {len(alpha_tokens)} 个 Alpha 代币")

        if not alpha_tokens:
            logger.warning("没有找到 Alpha 代币")
            return {}

        # 2. 获取交易所可交易的合约符号（含下架时点 delivery_date）
        tradable_symbols = self._get_tradable_symbols()
        logger.info(f"Step 2: 交易所共有 {len(tradable_symbols)} 个可交易合约对")

        # 3. 取交集（Alpha 代币中可合约交易的）
        #    市值依赖合约价，故必须先确定合约存在再算市值
        tradable_base_assets = {sym.removesuffix("USDT") for sym in tradable_symbols}
        tradable_alpha = {
            base: token for base, token in alpha_tokens.items()
            if base in tradable_base_assets
        }
        logger.info(f"Step 3: Alpha 代币与可交易合约的交集: {len(tradable_alpha)} 个")
        if not tradable_alpha:
            return {}

        # 4. 批量取合约最新价，算合约市值
        prices = self._get_contract_prices(list(
            f"{base}USDT" for base in tradable_alpha
        ))
        market_caps = {
            base: self._compute_market_cap(token, prices.get(f"{base}USDT"))
            for base, token in tradable_alpha.items()
        }

        # 5. 过滤 < 阈值
        candidate_symbols: dict[str, tuple[float, int]] = {}
        for base, market_cap in market_caps.items():
            if market_cap < self.MARKET_CAP_THRESHOLD:
                contract_symbol = f"{base}USDT"
                candidate_symbols[contract_symbol] = (market_cap, tradable_symbols[contract_symbol])

        logger.info(f"Step 4: 合约市值 < 5000 万的代币: {len(candidate_symbols)} 个")
        return candidate_symbols

    def _collect_alpha_tokens(self) -> dict[str, BinanceAlphaToken]:
        """收集 Alpha 代币（按 base_asset 索引），不做市值过滤。

        Returns:
            dict[base_asset -> BinanceAlphaToken]
        """
        tokens = self.client.get_alpha_tokens()
        result: dict[str, BinanceAlphaToken] = {}

        for token in tokens:
            base_asset = token.symbol.strip().upper()
            result[base_asset] = token

        return result

    def _get_contract_prices(self, symbols: list[str]) -> dict[str, float]:
        """批量获取合约最新价。

        一次性拉全部合约 ticker（不传 symbol），本地按需要的 symbol 取 last_price。
        避免逐个请求拖慢选币。

        Returns:
            dict[contract_symbol -> last_price]，无 ticker 的 symbol 不包含在结果中
        """
        if not symbols:
            return {}
        wanted = set(symbols)
        tickers = self.client.get_future_ticker_24hr()
        return {
            t.symbol: t.last_price_float
            for t in tickers
            if t.symbol in wanted
        }

    def _compute_market_cap(
        self, token: BinanceAlphaToken, contract_price: float | None
    ) -> float:
        """计算合约口径市值：circulating_supply × 合约价。

        降级策略：circulating_supply 缺失或合约价缺失时，用现货 marketCap 兜底。
        """
        if (
            token.circulating_supply is not None
            and contract_price is not None
            and contract_price > 0
        ):
            return float(token.circulating_supply) * contract_price
        # 降级：用现货 marketCap（可能为 None，转为 0.0 兜底）
        return token.market_cap if token.market_cap is not None else 0.0

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
