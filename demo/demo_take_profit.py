#!/usr/bin/env python3
"""为币安合约持仓批量下 +20% 止盈限价单（LIMIT + reduceOnly）。

安全设计：
- 默认 DRY-RUN，仅打印不下单；加 --execute 才真实下单
- 密钥从环境变量 BINANCE_API_KEY / BINANCE_API_SECRET 读取，不写进代码
- --execute 模式下二次确认

止盈单语义（LIMIT + reduceOnly）：
- 多头(long)  限价卖单，价 = 开仓价 × (1 + tp)，等价格上涨到限价成交
- 空头(short) 限价买单，价 = 开仓价 × (1 - tp)，等价格下跌到限价成交
- reduceOnly=true：确保只减仓不开新仓
- amount = 仓位数量（contracts）

注意：LIMIT 限价单直接挂订单簿，非条件单。
若多头止盈价已低于当前市价（已超止盈位），会立即成交。

运行示例:
    # DRY-RUN（默认，不下单）
    python demo_take_profit.py

    # 指定 30% 止盈
    python demo_take_profit.py --tp 0.3

    # 真实下单
    python demo_take_profit.py --execute
"""
from __future__ import annotations

import argparse
import os
import sys

import ccxt

# 止盈单默认参数
DEFAULT_TP_PCT = 0.2


def load_api_credentials() -> tuple[str, str]:
    """从环境变量读取 API 密钥。"""
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        print("❌ 未找到 API 密钥！请设置环境变量：")
        print("   export BINANCE_API_KEY=你的API_KEY")
        print("   export BINANCE_API_SECRET=你的API_SECRET")
        sys.exit(1)
    return api_key, api_secret


def create_exchange(api_key: str, api_secret: str) -> ccxt.binance:
    """构造鉴权版币安合约交易所实例。"""
    return ccxt.binance({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })


def calc_take_profit_price(entry_price: float, side: str, tp_pct: float) -> float:
    """根据仓位方向计算止盈限价。

    long  -> entryPrice × (1 + tp_pct)  （上涨 tp% 止盈）
    short -> entryPrice × (1 - tp_pct)  （下跌 tp% 止盈）
    """
    if side == "long":
        return entry_price * (1.0 + tp_pct)
    return entry_price * (1.0 - tp_pct)


def build_tp_order_params(position: dict, tp_pct: float) -> dict:
    """从持仓构造止盈限价单参数。

    LIMIT + reduceOnly：限价单挂在订单簿，等价格到限价成交。
    多头平仓用 sell（限价卖出），空头平仓用 buy（限价买入）。
    """
    side = position.get("side", "")
    entry_price = float(position.get("entryPrice") or 0)
    symbol = position.get("symbol", "")
    contracts = float(position.get("contracts") or 0)
    tp_price = calc_take_profit_price(entry_price, side, tp_pct)

    # 多头平仓用 sell，空头平仓用 buy
    close_side = "sell" if side == "long" else "buy"

    # positionSide：双向持仓(hedge mode)必须传 LONG/SHORT，
    # 单向持仓传 BOTH。从持仓的原始 positionSide 字段获取，兼容两种模式。
    raw_info = position.get("info") or {}
    position_side = raw_info.get("positionSide", "BOTH")

    # reduceOnly 只在单向持仓(BOTH)时传；
    # 双向持仓(LONG/SHORT)用 positionSide 定向，传 reduceOnly 会报 -1106。
    order_params: dict[str, object] = {
        "positionSide": position_side,
        "timeInForce": "GTC",  # Good Till Cancel，挂单直到取消或成交
    }
    if position_side == "BOTH":
        order_params["reduceOnly"] = True

    return {
        "symbol": symbol,
        "type": "LIMIT",
        "side": close_side,
        "amount": contracts,  # 限价单需指定数量（平掉整个仓位）
        "price": tp_price,
        "params": order_params,
        "tp_price": tp_price,  # 供打印用，非下单参数
    }


def fetch_active_positions(exchange: ccxt.binance) -> list[dict]:
    """获取所有有仓位量的持仓（过滤零仓位行）。"""
    positions = exchange.fetch_positions()
    active = [
        p for p in positions
        if p.get("contracts") and float(p["contracts"]) > 0
    ]
    return active


def print_positions_table(positions: list[dict], tp_pct: float) -> None:
    """打印持仓与止盈价表格。"""
    print()
    print(
        f"{'代币':<14} {'方向':<6} {'仓位量':>12} {'开仓价':>12} "
        f"{'止盈限价':>12} {'收益率':>8} {'未实现盈亏':>14}"
    )
    print("-" * 90)

    for pos in positions:
        symbol = pos.get("symbol", "")
        side = pos.get("side", "")
        contracts = float(pos.get("contracts") or 0)
        entry_price = float(pos.get("entryPrice") or 0)
        upnl = float(pos.get("unrealizedPnl") or 0)
        tp_price = calc_take_profit_price(entry_price, side, tp_pct)
        side_cn = "做多" if side == "long" else "做空"

        print(
            f"{symbol:<14} {side_cn:<6} {contracts:>12.4f} {entry_price:>12.4f} "
            f"{tp_price:>12.4f} {tp_pct*100:>7.0f}% {upnl:>+12.2f} USDT"
        )


def run_dry_run(positions: list[dict], tp_pct: float) -> None:
    """DRY-RUN 模式：仅打印，不下单。"""
    print_positions_table(positions, tp_pct)
    print()
    print(f"⏸️  DRY-RUN 模式：以上 {len(positions)} 张限价止盈单未实际下单")
    print("   订单类型: LIMIT + reduceOnly（挂限价单等成交）")
    print("   添加 --execute 参数以真实下单")


def run_execute(
    exchange: ccxt.binance, positions: list[dict], tp_pct: float,
) -> None:
    """EXECUTE 模式：真实下单。"""
    print()
    print(f"⚠️  EXECUTE 模式：将真实下单以下 {len(positions)} 张限价止盈单")
    print("   订单类型: LIMIT + reduceOnly（挂限价单等成交）")
    for i, pos in enumerate(positions, 1):
        symbol = pos.get("symbol", "")
        side = pos.get("side", "")
        contracts = float(pos.get("contracts") or 0)
        entry_price = float(pos.get("entryPrice") or 0)
        tp_price = calc_take_profit_price(entry_price, side, tp_pct)
        side_cn = "做多" if side == "long" else "做空"
        print(
            f"  {i}. {symbol:<14} {side_cn}  限价 {tp_price:.4f} "
            f"数量 {contracts:.4f} (开仓 {entry_price:.4f} +{tp_pct*100:.0f}%)"
        )

    print()
    confirm = input("确认下单？(yes/no): ").strip().lower()
    if confirm != "yes":
        print("已取消，未下单。")
        return

    print()
    success = 0
    failed = 0
    for pos in positions:
        symbol = pos.get("symbol", "")
        order_params = build_tp_order_params(pos, tp_pct)
        try:
            order = exchange.create_order(
                symbol=order_params["symbol"],
                type=order_params["type"],
                side=order_params["side"],
                amount=order_params["amount"],
                price=order_params["price"],
                params=order_params["params"],
            )
            order_id = order.get("id", "未知")
            print(f"✅ {symbol} 限价止盈单已下: orderId={order_id}")
            success += 1
        except Exception as e:  # noqa: BLE001
            print(f"❌ {symbol} 下单失败: {e}")
            failed += 1

    print()
    print(f"汇总: 成功 {success} 张, 失败 {failed} 张")


def main() -> None:
    """主函数。"""
    parser = argparse.ArgumentParser(description="为币安合约持仓批量下限价止盈单")
    parser.add_argument(
        "--tp", type=float, default=DEFAULT_TP_PCT,
        help=f"止盈率 (默认: {DEFAULT_TP_PCT}，即 {int(DEFAULT_TP_PCT*100)}%%)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="真实下单（默认 DRY-RUN 仅打印）",
    )
    parser.add_argument(
        "--symbol", type=str, default=None,
        help="只处理指定代币（如 BTCUSDT），用于测试单个 symbol 下单",
    )
    args = parser.parse_args()

    api_key, api_secret = load_api_credentials()
    print("🔑 已加载 API 密钥")

    exchange = create_exchange(api_key, api_secret)

    print("📊 获取合约持仓...")
    positions = fetch_active_positions(exchange)

    if not positions:
        print("ℹ️  当前无持仓（或全部为零仓位），无需下止盈单")
        return

    # 按指定 symbol 过滤（用于测试单个代币下单）
    # fetch_positions 返回 ccxt 统一格式（如 PUMPBTC/USDT:USDT），
    # 用户可能传币安原生格式（PUMPBTCUSDT）或统一格式，统一归一化比较。
    if args.symbol:
        target = args.symbol.upper().replace("/", "").replace(":", "")
        positions = [
            p for p in positions
            if p.get("symbol", "").upper().replace("/", "").replace(":", "") == target
        ]
        if not positions:
            print(f"ℹ️  持仓中未找到 {args.symbol}，请确认 symbol 正确且有持仓")
            return
        print(f"   已筛选出 {len(positions)} 个 {args.symbol} 持仓")
    else:
        print(f"   获取到 {len(positions)} 个持仓（已过滤零仓位）")

    if args.execute:
        run_execute(exchange, positions, args.tp)
    else:
        run_dry_run(positions, args.tp)


if __name__ == "__main__":
    main()

