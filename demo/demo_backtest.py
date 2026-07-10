#!/usr/bin/env python3
"""策略回测：每日检测 + 买入 10U + 无止损 + 止盈，扫描不同止盈率。

回测"持有到止盈或下架清算"的二元赌注策略，输出 TP-胜率-总盈亏曲线，
为选择止盈率提供数据支撑。

运行示例:
    # 默认回测最近 90 天
    python demo_backtest.py

    # 回测最近 60 天
    python demo_backtest.py --days 60
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from trading_service.clients import BinanceClient, BinanceFutureKline
from trading_service.pickers import (
    PERPETUAL_DELIVERY_SENTINEL,
    BacktestResult,
    BacktestTrade,
    PortfolioConfig,
    SignalEntry,
    TechnicalAnalyzer,
    scan_tp,
    simulate_portfolio,
)
from trading_service.pickers.symbol_picker import AlphaTokenSource
from trading_service.types import CrossSignalType

# 回测参数
SCAN_TP_VALUES = [0.1, 0.2, 0.3]  # 扫描的止盈率：10%/20%/30%
SMA_PERIOD = 200
KLINE_INTERVAL = "1d"
SIGNAL_CHECK_LAST_N = 10
PORTFOLIO_CONFIG = PortfolioConfig()  # 100U / 10U/笔 / 最多 10 仓


def setup_logging() -> None:
    """配置日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def fetch_all_daily_klines(
    client: BinanceClient, symbol: str, days: int,
) -> list[BinanceFutureKline]:
    """拉取某代币足够长的日 K 线（窗口 + SMA 预热）。

    需要 days + SMA_PERIOD + SIGNAL_CHECK_LAST_N 根，分页拉取（limit 上限 1500）。
    """
    total_needed = days + SMA_PERIOD + SIGNAL_CHECK_LAST_N
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - total_needed * 86_400_000

    all_klines: list[BinanceFutureKline] = []
    cursor = start_ms
    while cursor < end_ms:
        batch = client.get_future_klines(
            symbol=symbol, interval=KLINE_INTERVAL,
            limit=1500, start_time=cursor, end_time=end_ms,
        )
        if not batch:
            break
        all_klines.extend(batch)
        cursor = batch[-1].open_time + 86_400_000
        if len(batch) < 1500:
            break

    return all_klines


def detect_signals_for_date(
    analyzer: TechnicalAnalyzer, klines: list[BinanceFutureKline], target_date: datetime,
) -> str | None:
    """在 target_date 当天检测信号，返回信号类型或 None。

    用 target_date 及之前所有 K 线（至少 201 根）算 SMA + 穿越。
    符合"值得做多"的信号：金叉 / 靠近均线 / 底部横盘。
    """
    # 取 target_date 当天及之前的 K 线
    target_ms = int(target_date.timestamp() * 1000)
    klines_up_to = [k for k in klines if k.open_time <= target_ms + 86_400_000]
    if len(klines_up_to) < 201:
        return None

    signal = analyzer.detect_200sma_signal(
        klines_up_to, symbol="BT", check_last_n=SIGNAL_CHECK_LAST_N,
    )
    if signal is None:
        return None
    # 死叉不做多；金叉/靠近均线/横盘均可做多
    if signal.cross_type == CrossSignalType.DEAD:
        return None
    return signal.cross_type.value


def run_backtest(
    client: BinanceClient, days: int,
) -> tuple[dict[float, list[BacktestTrade]], int, int]:
    """执行回测，返回各 TP 的交易列表 + 候选数 + 跳过数。

    流程：
    1. 取 Alpha 小市值代币 + 流通量 + 可交易合约
    2. 拉历史日 K 线，预计算每日信号（哪天哪个币有做多信号）
    3. 每个 TP 各跑一次 simulate_portfolio（日级资金调度）
    """
    analyzer = TechnicalAnalyzer()

    # 1. 取当前 Alpha 代币（含流通量），用于历史市值近似
    logging.info("Step 1: 拉取 Alpha 代币列表...")
    source = AlphaTokenSource(client=client)
    alpha_tokens_below_cap = source._get_alpha_tokens_below_cap()  # noqa: SLF001
    all_alpha = client.get_alpha_tokens()
    circulating_by_base: dict[str, float] = {}
    for t in all_alpha:
        if t.circulating_supply is not None:
            try:
                circulating_by_base[t.symbol.strip().upper()] = float(t.circulating_supply)
            except (ValueError, TypeError):
                continue

    # 2. 取可交易永续合约（含 delivery_date）
    logging.info("Step 2: 拉取可交易永续合约...")
    tradable = source._get_tradable_symbols()  # noqa: SLF001

    # 3. 候选 = Alpha 小市值代币 ∩ 可交易永续合约
    candidates: list[tuple[str, float, int]] = []  # (symbol, circ_supply, delivery_date)
    for base_asset in alpha_tokens_below_cap:
        symbol = f"{base_asset}USDT"
        if symbol not in tradable:
            continue
        circ = circulating_by_base.get(base_asset, 0.0)
        if circ <= 0:
            continue
        candidates.append((symbol, circ, tradable[symbol]))
    logging.info(f"Step 3: 候选代币 {len(candidates)} 个")

    # 4. 拉历史日 K 线 + 预计算每日信号
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=days)

    klines_by_symbol: dict[str, list[BinanceFutureKline]] = {}
    delisting_by_symbol: dict[str, datetime | None] = {}
    signals_by_date: dict[datetime, list[SignalEntry]] = {}
    skipped = 0

    for idx, (symbol, circ_supply, delivery_date) in enumerate(candidates, 1):
        if idx % 20 == 0:
            logging.info(f"  拉K线进度: {idx}/{len(candidates)}")

        klines = fetch_all_daily_klines(client, symbol, days)
        if len(klines) < SMA_PERIOD + days:
            skipped += 1
            continue
        klines_by_symbol[symbol] = klines

        # 下架日
        delisting_by_symbol[symbol] = (
            datetime.fromtimestamp(delivery_date / 1000, tz=timezone.utc)
            if delivery_date != PERPETUAL_DELIVERY_SENTINEL else None
        )

        # 遍历窗口内每个交易日检测信号
        for kline in klines:
            kdate = datetime.fromtimestamp(kline.open_time / 1000, tz=timezone.utc)
            if kdate < window_start or kdate > window_end:
                continue
            # 用当前流通量 × 当日收盘价近似历史市值
            if circ_supply * kline.close_price_float >= AlphaTokenSource.MARKET_CAP_THRESHOLD:
                continue
            signal = detect_signals_for_date(analyzer, klines, kdate)
            if signal is None:
                continue
            signals_by_date.setdefault(kdate, []).append(
                SignalEntry(symbol=symbol, entry_price=kline.close_price_float)
            )

    total_signals = sum(len(v) for v in signals_by_date.values())
    logging.info(f"Step 4: 预计算信号完成，共 {total_signals} 个信号")

    # 5. 每个 TP 各跑一次资金约束模拟
    trades_by_tp: dict[float, list[BacktestTrade]] = {}
    for tp in SCAN_TP_VALUES:
        logging.info(f"  模拟 TP={tp*100:.0f}%...")
        trades_by_tp[tp] = simulate_portfolio(
            signals_by_date=signals_by_date,
            klines_by_symbol=klines_by_symbol,
            delisting_by_symbol=delisting_by_symbol,
            tp_pct=tp, config=PORTFOLIO_CONFIG, window_end=window_end,
        )

    return trades_by_tp, len(candidates), skipped


def print_results(
    results: list[BacktestResult], days: int,
    candidate_count: int, skipped_count: int, duration: float,
) -> None:
    """打印回测结果。"""
    print()
    print("=" * 100)
    print("                       📊 止盈率回测报告（资金约束）")
    print("=" * 100)
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(days=days)
    print(f"回测窗口: {window_start:%Y-%m-%d} ~ {window_end:%Y-%m-%d} ({days} 天)")
    print(
        f"资金约束: 总资金 {PORTFOLIO_CONFIG.total_capital_usdt:.0f}U / "
        f"每笔 {PORTFOLIO_CONFIG.position_size_usdt:.0f}U / "
        f"最多 {PORTFOLIO_CONFIG.max_positions} 仓"
    )
    print(f"候选代币: {candidate_count} 个 | 跳过(K线不足): {skipped_count} 个")
    print(f"⏱️   耗时: {duration:.1f} 秒")
    print()
    print("⚠️ 偏差声明:")
    print("  - 市值用「当前流通量 × 历史价格」近似（流通量无历史数据）")
    print("  - Alpha 代币身份用当前列表，存在前视偏差")
    print("  - 已下架且 K 线丢失的代币无法覆盖（生存者偏差）")
    print("  - 下架清算价用下架日收盘价近似（实际为结算价）")
    print()
    print("止盈率扫描:")
    print(
        f"{'TP%':<6} {'交易数':<8} {'胜':<6} {'负':<6} {'未决':<6} "
        f"{'胜率':<8} {'已实现(U)':<12} {'未实现(U)':<12} {'总盈亏(U)':<12} {'持仓(天)':<10}"
    )
    print("-" * 100)

    for r in results:
        print(
            f"{r.tp_pct*100:>4.0f}% "
            f"{r.total_trades:<8} {r.wins:<6} {r.losses:<6} {r.open_trades:<6} "
            f"{r.win_rate*100:>6.1f}%  "
            f"{r.realized_pnl_usdt:>+10.1f}   "
            f"{r.unrealized_pnl_usdt:>+10.1f}   "
            f"{r.total_pnl_usdt:>+10.1f}   "
            f"{r.avg_hold_days:>6.1f}"
        )

    print()
    print("=" * 95)
    print("说明:")
    print("  已实现 = 止盈盈利 + 下架清算亏损")
    print("  未实现 = 未决仓位按窗口最后收盘价结算的浮盈浮亏")
    print("  总盈亏 = 已实现 + 未实现")
    print()
    # 找最优 TP（总盈亏最大）
    if results:
        best = max(results, key=lambda r: r.total_pnl_usdt)
        if best.total_trades > 0:
            print(
                f"💡 总盈亏最优止盈率: {best.tp_pct*100:.0f}% "
                f"(胜率 {best.win_rate*100:.1f}%, "
                f"已实现 {best.realized_pnl_usdt:+.1f} U, "
                f"未实现 {best.unrealized_pnl_usdt:+.1f} U, "
                f"总盈亏 {best.total_pnl_usdt:+.1f} U)"
            )
            breakeven_winrate = 1.0 / (1.0 + best.tp_pct) * 100
            print(
                f"   该 TP 的盈亏平衡胜率: {breakeven_winrate:.1f}%"
                f"（实际 {best.win_rate*100:.1f}%）"
            )
        else:
            print("⚠️ 无有效交易，无法给出建议")


async def main() -> None:
    """主函数。"""
    parser = argparse.ArgumentParser(description="止盈率回测")
    parser.add_argument(
        "--days", type=int, default=90,
        help="回测窗口天数 (默认: 90)",
    )
    args = parser.parse_args()

    setup_logging()
    start_time = time.time()

    with BinanceClient(timeout=30) as client:
        trades_by_tp, candidate_count, skipped_count = run_backtest(client, args.days)

    results = scan_tp(trades_by_tp)
    duration = time.time() - start_time
    print_results(results, args.days, candidate_count, skipped_count, duration)


if __name__ == "__main__":
    asyncio.run(main())
