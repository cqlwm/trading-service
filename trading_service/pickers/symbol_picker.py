from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from trading_service.clients import BinanceClient
from trading_service.pickers.technical_analyzer import (
    ITechnicalAnalyzer,
    TechnicalAnalyzer,
)

logger = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    """代币信息。

    注意：同时支持两种使用场景：
    - 简单选币器：只需要 symbol, price, volume_24h 等
    - Alpha技术分析选币器：包含完整的市值、K线、技术指标等
    """

    # === 基础字段（所有选币器通用）===
    symbol: str  # 交易对符号（如 BTCUSDT）
    price: float = 0.0  # 当前价格
    volume_24h: float = 0.0  # 24小时成交量
    market_cap: float = 0.0  # 市值（USDT）
    price_change_pct_24h: float = 0.0  # 24小时涨跌幅

    # === Alpha选币器扩展字段 ===
    base_asset: str = ""  # 基础资产（如 BTC）
    yesterday_change_percent: float = 0.0  # 昨日涨跌幅（%）
    yesterday_open: float = 0.0  # 昨日开盘价
    yesterday_close: float = 0.0  # 昨日收盘价

    # === 技术分析字段 ===
    sma_200: float | None = None  # 200均线价格
    price_vs_sma200_percent: float | None = None  # 价格相对均线的距离%
    cross_signal: str | None = None  # 穿越信号: golden/dead/near/None
    cross_ago: int | None = None  # 多少根K线之前穿越的
    is_sideways_bottom: bool = False  # 是否底部横盘
    volatility_10: float | None = None  # 最近10根K线波动率%


class ISymbolPicker(ABC):
    """选币器接口。"""

    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:
        """筛选符合条件的币种。"""
        ...


class StaticListSymbolPicker(ISymbolPicker):
    """静态列表币种选择器。

    兼容策略框架的 async 接口。
    """

    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols

    async def pick(self) -> list[SymbolInfo]:
        """返回静态的币种列表。"""
        return [
            SymbolInfo(
                symbol=s,
                price=0.0,
                volume_24h=0.0,
                market_cap=0.0,
                price_change_pct_24h=0.0,
            )
            for s in self.symbols
        ]


class SimpleAlphaSymbolPicker(ISymbolPicker):
    """简单 Alpha 代币选币器。

    筛选条件:
    1. Alpha 代币，市值 5000 万 USDT 以下
    2. 在合约交易所存在且处于可交易状态
    3. 昨日 K 线为上涨（收盘价 >= 开盘价）
    4. [可选] 200均线附近，底部横盘或刚突破
    """

    MARKET_CAP_THRESHOLD = 50_000_000.0  # 5000 万 USDT
    INTERVAL_1D = "1d"  # 日 K 线
    INTERVAL_4H = "4h"  # 4小时 K 线

    def __init__(
        self,
        client: BinanceClient | None = None,
        enable_technical_filter: bool = False,
        kline_interval: str = "4h",
        analyzer: ITechnicalAnalyzer | None = None,
    ) -> None:
        self.client = client or BinanceClient(timeout=30)
        self.enable_technical_filter = enable_technical_filter
        self.kline_interval = kline_interval
        # 依赖注入：便于单元测试时替换为 mock analyzer
        self.analyzer: ITechnicalAnalyzer = analyzer or TechnicalAnalyzer()

    async def pick(self) -> list[SymbolInfo]:
        """筛选符合条件的代币（async 接口）。"""
        # 同步IO用线程池包装，兼容async框架
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._pick_sync)

    def _pick_sync(self) -> list[SymbolInfo]:
        """筛选符合条件的代币（同步实现）。"""
        logger.info("开始筛选 Alpha 代币...")
        if self.enable_technical_filter:
            logger.info(f"✅ 已启用技术分析筛选，K线周期: {self.kline_interval}")

        # 1-3. 基础筛选
        candidate_symbols = self._get_base_candidates()
        if not candidate_symbols:
            return []

        # 4. 获取昨日 K 线判断涨跌 + 技术分析
        result = self._filter_with_analysis(candidate_symbols)
        logger.info(f"最终筛选结果: 共 {len(result)} 个代币符合条件")
        return result

    def _get_base_candidates(self) -> dict[str, float]:
        """获取基础候选池：Alpha代币 + 5000万以下 + 合约可交易。"""
        # 1. 获取 Alpha 代币列表并按市值过滤
        alpha_tokens = self._get_alpha_tokens_below_cap()
        logger.info(f"Step 1: 获取到 {len(alpha_tokens)} 个市值 5000 万以下的 Alpha 代币")

        if not alpha_tokens:
            logger.warning("没有找到符合市值条件的 Alpha 代币")
            return {}

        # 2. 获取交易所可交易的合约符号
        tradable_symbols = self._get_tradable_symbols()
        logger.info(f"Step 2: 交易所共有 {len(tradable_symbols)} 个可交易合约对")

        # 3. 取交集（Alpha 代币中可合约交易的）
        candidate_symbols: dict[str, float] = {}
        for base_asset, market_cap in alpha_tokens.items():
            contract_symbol = f"{base_asset}USDT"
            if contract_symbol in tradable_symbols:
                candidate_symbols[contract_symbol] = market_cap

        logger.info(f"Step 3: Alpha 代币与可交易合约的交集: {len(candidate_symbols)} 个")
        return candidate_symbols

    def _filter_with_analysis(self, candidate_symbols: dict[str, float]) -> list[SymbolInfo]:
        """K线分析 + 技术筛选。"""
        result: list[SymbolInfo] = []
        symbols = list(candidate_symbols.keys())

        logger.info(f"Step 4: 开始获取K线并分析技术形态...")

        for idx, symbol in enumerate(symbols, 1):
            try:
                info = self._analyze_symbol(symbol, candidate_symbols[symbol])
                if info:
                    result.append(info)

                # 每处理10个打印进度
                if idx % 10 == 0:
                    logger.info(f"  进度: {idx}/{len(symbols)} 已分析")

            except Exception as e:  # noqa: BLE001
                logger.debug(f"{symbol}: 分析失败 - {e}")

        # 按市值排序（从小到大）
        result.sort(key=lambda x: x.market_cap)
        return result

    def _analyze_symbol(self, symbol: str, market_cap: float) -> SymbolInfo | None:
        """分析单个代币，返回筛选通过的代币信息。"""
        # 1. 获取昨日日K线判断涨跌（获取5根足够）
        klines_1d = self.client.get_future_klines(
            symbol=symbol,
            interval=self.INTERVAL_1D,
            limit=5,
        )

        if len(klines_1d) < 2:
            return None

        yesterday_kline = klines_1d[-2]
        if not yesterday_kline.is_up:
            return None

        # 构建基础信息
        base_asset = symbol.replace("USDT", "")
        info = SymbolInfo(
            symbol=symbol,
            base_asset=base_asset,
            market_cap=market_cap,
            yesterday_change_percent=yesterday_kline.price_change_percent_float,
            yesterday_open=yesterday_kline.open_price_float,
            yesterday_close=yesterday_kline.close_price_float,
            price=yesterday_kline.close_price_float,
            price_change_pct_24h=yesterday_kline.price_change_percent_float,
        )

        # 2. 如果启用技术分析，获取更多K线计算
        if self.enable_technical_filter:
            klines = self.client.get_future_klines(
                symbol=symbol,
                interval=self.kline_interval,
                limit=210,  # 需要201根计算SMA200
            )

            signal = self.analyzer.detect_200sma_signal(klines, symbol)
            if signal:
                info.sma_200 = signal.sma_200
                info.price_vs_sma200_percent = signal.distance_percent
                info.cross_signal = signal.cross_type
                info.cross_ago = signal.cross_ago
                info.volatility_10 = signal.volatility_10
                info.is_sideways_bottom = signal.is_sideways

        return info

    def _get_alpha_tokens_below_cap(self) -> dict[str, float]:
        """获取市值 5000 万以下的 Alpha 代币。"""
        tokens = self.client.get_alpha_tokens()
        result: dict[str, float] = {}

        for token in tokens:
            if token.market_cap is not None and token.market_cap < self.MARKET_CAP_THRESHOLD:
                base_asset = token.symbol.strip().upper()
                result[base_asset] = token.market_cap

        return result

    def _get_tradable_symbols(self) -> set[str]:
        """获取交易所所有可交易的合约符号。"""
        exchange_info = self.client.get_future_exchange_info()
        tradable: set[str] = set()

        for symbol_info in exchange_info.symbols:
            if (
                symbol_info.status == "TRADING"
                and symbol_info.quote_asset == "USDT"
            ):
                tradable.add(symbol_info.symbol)

        return tradable
