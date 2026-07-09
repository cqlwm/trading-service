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

from trading_service.clients import BinanceClient
from trading_service.pickers import (
    AlphaTokenSource,
    SelectionPipeline,
    SymbolInfo,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
)


def setup_logging() -> None:
    """配置日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


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
    if info.cross_signal == "golden":
        return "🔥"
    elif info.cross_signal == "dead":
        return "🔻"
    elif info.cross_signal == "near":
        return "⚡"
    return "  "


def print_sideways_icon(info: SymbolInfo) -> str:
    """横盘图标。"""
    return "⏸️" if info.is_sideways_bottom else "  "


def print_results(results: list[SymbolInfo], duration: float, interval: str) -> None:
    """打印筛选结果。"""
    if not results:
        print("⚠️  暂无符合条件的代币")
        return

    # 统计各类信号
    golden = sum(1 for r in results if r.cross_signal == "golden")
    near = sum(1 for r in results if r.cross_signal == "near")
    sideways = sum(1 for r in results if r.is_sideways_bottom)

    print(f"✅ 筛选完成，共 {len(results)} 个代币符合条件")
    print(f"   - 刚突破均线: {golden} 个")
    print(f"   - 靠近均线附近: {near} 个")
    print(f"   - 底部横盘: {sideways} 个")
    print(f"⏱️   耗时: {duration:.1f} 秒")
    print()

    # 打印表头
    header = (
        f"{'排名':<4} {'代币':<12} {'市值(万)':>12} "
        f"{'昨日涨幅':>10} {'当前价':>10} {'SMA200':>10} {'距离%':>8} "
        f"{'波动%':>7} {'突破':<5} {'横盘':<5}"
    )
    print(header)
    print("-" * 95)

    for i, info in enumerate(results, 1):
        market_cap_wan = info.market_cap / 10000
        cross_icon = print_cross_icon(info)
        sideways_icon = print_sideways_icon(info)

        # 格式化距离均线百分比
        dist_str = f"{info.price_vs_sma200_percent:+.2f}%" if info.price_vs_sma200_percent else "N/A"
        vol_str = f"{info.volatility_10:.1f}%" if info.volatility_10 else "N/A"
        price_str = f"{info.yesterday_close:.4f}"

        print(
            f"{i:<4} "
            f"{info.base_asset:<12} "
            f"{market_cap_wan:>10,.1f}万 "
            f"{info.yesterday_change_percent:>+9.2f}% "
            f"{price_str:>10} "
            f"{info.sma_200 or 'N/A':>10} "
            f"{dist_str:>8} "
            f"{vol_str:>7} "
            f"{cross_icon:<5} "
            f"{sideways_icon:<5}"
        )

    print()
    print("=" * 90)
    print("图标说明:")
    print("  🔥 金叉突破   ⚡ 靠近均线   🔻 死叉   ⏸️ 底部横盘")
    print()
    print("策略建议:")
    print("  1. 优先关注 🔥刚突破均线 + ⏸️底部横盘的标的")
    print("  2. 波动率越小（横盘越久），突破后潜力可能越大")
    print("  3. 小市值代币波动大，注意仓位管理")


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
