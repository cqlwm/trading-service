#!/usr/bin/env python3
"""AlphaTokenSource 演示脚本（基础选币，不含技术分析）。

运行示例:
    python demo_picker.py
"""
from __future__ import annotations

import asyncio
import logging
import time

from trading_service.clients import BinanceClient
from trading_service.pickers import AlphaTokenSource, SymbolInfo


def setup_logging() -> None:
    """配置日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


def print_header() -> None:
    """打印标题。"""
    print()
    print("=" * 80)
    print("                        Alpha 代币筛选器")
    print("=" * 80)
    print()
    print("筛选条件:")
    print("  ✅ 币安 Alpha 代币")
    print("  ✅ 市值 < 5000 万 USDT")
    print("  ✅ 有 USDT 永续合约可交易")
    print("  ✅ 昨日 K 线为阳线（收盘价 >= 开盘价）")
    print()


def print_results(results: list[SymbolInfo], duration: float) -> None:
    """打印筛选结果。"""
    if not results:
        print("⚠️  暂无符合条件的代币")
        return

    print(f"✅ 筛选完成，共 {len(results)} 个代币符合条件")
    print(f"⏱️   耗时: {duration:.2f} 秒")
    print()

    # 打印表头
    header = (
        f"{'排名':<4} {'代币':<12} {'合约':<15} {'市值(万)':>12} "
        f"{'价格':>10} {'涨跌幅':>10} {'涨跌':<6}"
    )
    print(header)
    print("-" * 85)

    for i, info in enumerate(results, 1):
        up_down = "📈" if info.price_change_pct_24h >= 0 else "📉"
        market_cap_wan = info.market_cap / 10000
        print(
            f"{i:<4} "
            f"{info.base_asset:<12} "
            f"{info.symbol:<15} "
            f"{market_cap_wan:>10,.1f}万 "
            f"{info.price:>10.4f} "
            f"{info.price_change_pct_24h:>+9.2f}% "
            f"{up_down:<6}"
        )

    print()
    print("=" * 80)
    print(f"统计: 共 {len(results)} 个代币，平均涨跌幅: "
          f"{sum(r.price_change_pct_24h for r in results) / len(results):.2f}%")


async def main() -> None:
    """主函数。"""
    setup_logging()
    print_header()

    start_time = time.time()

    with BinanceClient(timeout=30) as client:
        picker = AlphaTokenSource(client=client)
        results = await picker.fetch()

    duration = time.time() - start_time
    print()
    print_results(results, duration)


if __name__ == "__main__":
    asyncio.run(main())
