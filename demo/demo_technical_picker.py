#!/usr/bin/env python3
"""技术分析选币器 - 200均线突破 + 底部横盘检测。

运行示例:
    # 4小时周期（推荐，平衡灵敏度和噪音）
    python demo_technical_picker.py

    # 日线周期（更保守）
    python demo_technical_picker.py --interval 1d
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import datetime, timezone

from trading_service.clients import BinanceClient
from trading_service.pickers import (
    AlphaTokenSource,
    SelectionPipeline,
    SymbolInfo,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
    is_delisting_soon,
    is_notable_signal,
)
from trading_service.types import CrossSignalType


def setup_logging() -> None:
    """配置日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def _latest_indicators(info: SymbolInfo) -> dict:
    """从 klines["4h"] 最后一行提取指标字典。无 4h 数据时返回空 dict。"""
    df = info.klines.get("4h")
    if df is None or len(df) == 0:
        return {}
    row = df.iloc[-1]
    return {col: row.get(col) for col in row.index}


def print_header(interval: str) -> None:
    """打印标题。"""
    print()
    print("=" * 90)
    print("                     📊 Alpha 技术分析选币器")
    print("=" * 90)
    print()
    print(f"📈 技术指标: SMA200 均线突破检测 ({interval} 周期)")
    print()
    print("筛选条件:")
    print("  ✅ 币安 Alpha 代币")
    print("  ✅ 市值 < 5000 万 USDT")
    print("  ✅ 有 USDT 永续合约可交易")
    print("  ✅ 昨日 K 线为阳线")
    print("  ✅ 最近10根K线穿越200均线 或 价格在均线 ±5% 范围内")
    print("  🎯 额外标记: 底部横盘(波动率<20%)")
    print()


def print_cross_icon(info: SymbolInfo) -> str:
    """根据信号类型返回图标。"""
    cross = _latest_indicators(info).get("cross_signal")
    if cross == CrossSignalType.GOLDEN.value:
        return "🔥"
    elif cross == CrossSignalType.DEAD.value:
        return "🔻"
    elif cross == CrossSignalType.NEAR.value:
        return "⚡"
    return "  "


def print_sideways_icon(info: SymbolInfo) -> str:
    """横盘图标。"""
    sideways = _latest_indicators(info).get("is_sideways_bottom")
    return "⏸️" if sideways and bool(sideways) else "  "


def delisting_label(info: SymbolInfo) -> str:
    """下架预警标签：即将下架显示 ⚠️ + 月-日，否则空。"""
    if not is_delisting_soon(info) or info.delivery_date is None:
        return ""
    dt = datetime.fromtimestamp(info.delivery_date / 1000, tz=timezone.utc)
    return f"⚠️{dt:%m-%d}"


def print_results(results: list[SymbolInfo], duration: float, interval: str) -> None:
    """打印筛选结果。"""
    # 只展示三类关注信号：金叉 / 靠近均线 / 底部横盘
    # picker 的过滤器是「纯增强不丢弃」（保留死叉/无信号），此处按展示需要过滤
    notable = [r for r in results if is_notable_signal(r)]
    if not notable:
        print("⚠️  暂无符合展示条件的代币（金叉 / 靠近均线 / 底部横盘）")
        return

    # 统计各类信号
    golden = sum(1 for r in notable if _latest_indicators(r).get("cross_signal") == CrossSignalType.GOLDEN.value)
    near = sum(1 for r in notable if _latest_indicators(r).get("cross_signal") == CrossSignalType.NEAR.value)
    sideways = sum(1 for r in notable if _latest_indicators(r).get("is_sideways_bottom") and bool(_latest_indicators(r).get("is_sideways_bottom")))
    delisting = sum(1 for r in notable if is_delisting_soon(r))

    print(f"✅ 筛选完成，共 {len(notable)} 个代币符合展示条件")
    print(f"   - 刚突破均线: {golden} 个")
    print(f"   - 靠近均线附近: {near} 个")
    print(f"   - 底部横盘: {sideways} 个")
    if delisting:
        print(f"   - ⚠️ 即将下架: {delisting} 个（注意规避）")
    print(f"⏱️   耗时: {duration:.1f} 秒")
    print()

    # 打印表头
    header = (
        f"{'排名':<4} {'代币':<12} {'市值(万)':>12} "
        f"{'涨跌幅':>10} {'当前价':>10} {'SMA200':>10} {'距离%':>8} "
        f"{'波动%':>7} {'突破':<5} {'横盘':<5} {'下架':<8}"
    )
    print(header)
    print("-" * 105)

    for i, info in enumerate(notable, 1):
        market_cap_wan = info.market_cap / 10000
        cross_icon = print_cross_icon(info)
        sideways_icon = print_sideways_icon(info)
        ind = _latest_indicators(info)

        # 格式化距离均线百分比
        price_vs_sma = ind.get("price_vs_sma200_percent")
        dist_str = f"{price_vs_sma:+.2f}%" if price_vs_sma else "N/A"
        vol_10 = ind.get("volatility_10")
        vol_str = f"{vol_10:.1f}%" if vol_10 else "N/A"
        price_str = f"{info.price:.4f}"
        sma = ind.get("sma_200")
        sma_str = f"{sma}" if sma else "N/A"

        print(
            f"{i:<4} "
            f"{info.base_asset:<12} "
            f"{market_cap_wan:>10,.1f}万 "
            f"{info.price_change_pct_24h:>+9.2f}% "
            f"{price_str:>10} "
            f"{sma_str:>10} "
            f"{dist_str:>8} "
            f"{vol_str:>7} "
            f"{cross_icon:<5} "
            f"{sideways_icon:<5} "
            f"{delisting_label(info):<8}"
        )

    print()
    print("=" * 90)
    print("图标说明:")
    print("  🔥 金叉突破   ⚡ 靠近均线   ⏸️ 底部横盘   ⚠️ 即将下架(月-日)")
    print()
    print("策略建议:")
    print("  1. 优先关注 🔥刚突破均线 + ⏸️底部横盘的标的")
    print("  2. 波动率越小（横盘越久），突破后潜力可能越大")
    print("  3. ⚠️ 即将下架的标的务必规避，切勿入场")
    print("  4. 小市值代币波动大，注意仓位管理")


async def main() -> None:
    """主函数。"""
    parser = argparse.ArgumentParser(description="Alpha技术分析选币器")
    parser.add_argument(
        "--interval",
        type=str,
        default="4h",
        choices=["1h", "4h", "1d"],
        help="K线周期: 1h/4h/1d (默认: 4h)",
    )
    args = parser.parse_args()

    setup_logging()
    print_header(args.interval)

    start_time = time.time()

    with BinanceClient(timeout=30) as client:
        picker = SelectionPipeline(
            source=AlphaTokenSource(client=client),
            filters=[
                TechnicalAnalysisFilter(
                    analyzer=TechnicalAnalyzer(),
                    client=client,
                    kline_interval=args.interval,
                ),
            ],
        )
        results = await picker.pick()

    duration = time.time() - start_time
    print()
    print_results(results, duration, args.interval)


if __name__ == "__main__":
    asyncio.run(main())
