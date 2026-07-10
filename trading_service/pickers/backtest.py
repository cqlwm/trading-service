"""回测核心逻辑：模拟"买入后持有，止盈或下架清算"的二元赌注策略。

纯函数 + 数据类，不依赖网络。网络数据获取由 demo 脚本负责，
回测逻辑只接收已拉好的历史 K 线列表。

策略语义：
- 无止损，每笔 10U
- win  = 价格触及 +TP% 止盈出场
- loss = 持有到下架日，以下架日收盘价近似清算
- open = K 线用完仍未触发（窗口内未决）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from trading_service.clients import BinanceFutureKline

POSITION_SIZE_USDT = 10.0


@dataclass
class SignalEntry:
    """单日信号：某代币在某日的入场信号。"""

    symbol: str
    entry_price: float


@dataclass
class OpenPosition:
    """回测中未平仓的仓位（按日推进时逐根 K 线检查）。"""

    symbol: str
    entry_date: datetime
    entry_price: float
    tp_pct: float


@dataclass
class PortfolioConfig:
    """资金约束配置。"""

    total_capital_usdt: float = 100.0
    position_size_usdt: float = 10.0
    max_positions: int = 10


@dataclass
class BacktestTrade:
    """单笔回测交易。"""

    symbol: str
    entry_date: datetime  # 买入日
    entry_price: float
    exit_date: datetime | None  # None=未决(窗口结束)
    exit_price: float | None  # 未决时=final_price（窗口最终价）
    outcome: str  # "win" | "loss" | "open"
    tp_pct: float  # 该笔对应的止盈率
    pnl_usdt: float  # 盈亏(USDT)，基于 10U 仓位；未决时为未实现盈亏
    hold_days: int
    realized: bool = True  # 是否已实现（win/loss=True，open=False）


@dataclass
class BacktestResult:
    """单个 TP 值的回测汇总。"""

    tp_pct: float
    total_trades: int
    wins: int
    losses: int
    open_trades: int  # 未决
    win_rate: float  # wins / (wins + losses)，open 不计入分母
    realized_pnl_usdt: float  # 已实现盈亏（win + loss）
    unrealized_pnl_usdt: float  # 未实现盈亏（open，按窗口最终价）
    total_pnl_usdt: float  # = realized + unrealized
    avg_hold_days: float


def _kline_date(kline: BinanceFutureKline) -> datetime:
    """K 线的日期（UTC，按 open_time 取当天 00:00 用于日期比较）。"""
    return datetime.fromtimestamp(kline.open_time / 1000, tz=timezone.utc)


def _check_position_on_day(
    entry_price: float,
    tp_pct: float,
    kline: BinanceFutureKline,
    kline_date: datetime,
    delisting_date: datetime | None,
) -> str | None:
    """检查单笔仓位在某日是否触发止盈/下架。

    判定优先级：止盈(high 触及止盈价) > 下架(当日 >= 下架日)。
    未触发返回 None。供 simulate_trade 与 simulate_portfolio 共用。
    """
    tp_price = entry_price * (1.0 + tp_pct)
    # 1. 止盈：当日最高价触及止盈价
    if kline.high_price_float >= tp_price:
        return "win"
    # 2. 下架：当日日期到达下架日（止盈未触发时）
    if delisting_date is not None and kline_date >= delisting_date:
        return "loss"
    return None


def simulate_trade(
    klines: list[BinanceFutureKline],
    entry_price: float,
    tp_pct: float,
    delisting_date: datetime | None,
    symbol: str,
    entry_date: datetime,
    final_price: float | None = None,
) -> BacktestTrade:
    """模拟单笔交易：逐日扫描买入后 K 线，判定止盈/下架/未决。

    判定优先级（逐日）：
    1. 当日 high_price >= 止盈价 -> win（止盈优先，即使当天也是下架日）
    2. 当日日期 >= 下架日 -> loss（exit_price=当日收盘价）
    3. K 线用完 -> open（未决，按 final_price 结算未实现盈亏）

    Args:
        klines: 买入日之后的 K 线（不含买入日）
        entry_price: 买入价
        tp_pct: 止盈率（如 0.5 = 50%）
        delisting_date: 下架日；None 表示未下架
        symbol: 交易对
        entry_date: 买入日
        final_price: 窗口最终价；未决仓位按此价结算未实现盈亏。
                     None 时未决 pnl=0（兼容旧契约）。

    Returns:
        BacktestTrade
    """
    tp_price = entry_price * (1.0 + tp_pct)

    for i, kline in enumerate(klines, 1):
        outcome = _check_position_on_day(
            entry_price=entry_price, tp_pct=tp_pct, kline=kline,
            kline_date=_kline_date(kline), delisting_date=delisting_date,
        )
        if outcome == "win":
            return BacktestTrade(
                symbol=symbol, entry_date=entry_date, entry_price=entry_price,
                exit_date=_kline_date(kline), exit_price=tp_price,
                outcome="win", tp_pct=tp_pct,
                pnl_usdt=POSITION_SIZE_USDT * tp_pct, hold_days=i, realized=True,
            )
        if outcome == "loss":
            exit_price = kline.close_price_float
            pnl = POSITION_SIZE_USDT * (exit_price / entry_price - 1.0)
            return BacktestTrade(
                symbol=symbol, entry_date=entry_date, entry_price=entry_price,
                exit_date=_kline_date(kline), exit_price=exit_price,
                outcome="loss", tp_pct=tp_pct, pnl_usdt=pnl, hold_days=i, realized=True,
            )

    # 3. 未决：按 final_price 结算未实现盈亏
    if final_price is not None:
        unrealized_pnl = POSITION_SIZE_USDT * (final_price / entry_price - 1.0)
    else:
        unrealized_pnl = 0.0
    return BacktestTrade(
        symbol=symbol, entry_date=entry_date, entry_price=entry_price,
        exit_date=None, exit_price=final_price,
        outcome="open", tp_pct=tp_pct, pnl_usdt=unrealized_pnl,
        hold_days=len(klines), realized=False,
    )


def summarize(trades: list[BacktestTrade], tp_pct: float) -> BacktestResult:
    """汇总某 TP 下的胜率与盈亏。

    胜率 = wins / (wins + losses)；open 不计入分母。无已决交易时胜率为 0。
    总盈亏 = 已实现(win+loss) + 未实现(open，按窗口最终价)。
    """
    wins = sum(1 for t in trades if t.outcome == "win")
    losses = sum(1 for t in trades if t.outcome == "loss")
    open_trades = sum(1 for t in trades if t.outcome == "open")
    decided = wins + losses
    win_rate = wins / decided if decided > 0 else 0.0
    realized_pnl = sum(t.pnl_usdt for t in trades if t.realized)
    unrealized_pnl = sum(t.pnl_usdt for t in trades if not t.realized)
    avg_hold = sum(t.hold_days for t in trades) / len(trades) if trades else 0.0

    return BacktestResult(
        tp_pct=tp_pct, total_trades=len(trades),
        wins=wins, losses=losses, open_trades=open_trades,
        win_rate=win_rate,
        realized_pnl_usdt=realized_pnl, unrealized_pnl_usdt=unrealized_pnl,
        total_pnl_usdt=realized_pnl + unrealized_pnl, avg_hold_days=avg_hold,
    )


def scan_tp(trades_by_tp: dict[float, list[BacktestTrade]]) -> list[BacktestResult]:
    """扫描多个 TP，返回汇总列表（按 TP 升序）。"""
    results = [summarize(trades, tp) for tp, trades in trades_by_tp.items()]
    results.sort(key=lambda r: r.tp_pct)
    return results


def _build_kline_index(
    klines_by_symbol: dict[str, list[BinanceFutureKline]],
) -> dict[str, dict[datetime, BinanceFutureKline]]:
    """构建 symbol -> {date -> kline} 索引，便于按日查找。"""
    index: dict[str, dict[datetime, BinanceFutureKline]] = {}
    for symbol, klines in klines_by_symbol.items():
        index[symbol] = {_kline_date(k): k for k in klines}
    return index


def _all_dates(
    signals_by_date: dict[datetime, list[SignalEntry]],
    kline_index: dict[str, dict[datetime, BinanceFutureKline]],
    window_end: datetime,
) -> list[datetime]:
    """收集需要遍历的所有日期：信号日 + K 线日（不晚于窗口结束），升序。"""
    dates: set[datetime] = set(signals_by_date.keys())
    for sym_klines in kline_index.values():
        dates.update(d for d in sym_klines.keys() if d <= window_end)
    return sorted(dates)


def simulate_portfolio(
    signals_by_date: dict[datetime, list[SignalEntry]],
    klines_by_symbol: dict[str, list[BinanceFutureKline]],
    delisting_by_symbol: dict[str, datetime | None],
    tp_pct: float,
    config: PortfolioConfig,
    window_end: datetime,
) -> list[BacktestTrade]:
    """日级资金调度模拟：按日推进，维护资金池与仓位池。

    每日逻辑（按时间顺序）：
    1. 平仓检查：遍历未平仓仓位，用当日 K 线判定止盈/下架
       - 止盈 -> 释放本金（cash += position_size），利润计入 realized
       - 下架 -> 不释放资金（已亏），亏损计入 realized
    2. 开仓检查：当天有信号的代币，若 cash >= position_size 且 持仓数 < max -> 开仓
    3. 窗口结束：剩余未平仓仓位按 final_price 结算未实现盈亏

    Args:
        signals_by_date: 每日信号（哪天、哪个币、入场价）
        klines_by_symbol: 各代币的 K 线列表（含买入日，按时间升序）
        delisting_by_symbol: 各代币下架日；None 表示未下架
        tp_pct: 止盈率
        config: 资金约束配置
        window_end: 窗口结束日（不含），未平仓仓位按此前最后可用价结算

    Returns:
        所有已平仓 + 未平仓的 BacktestTrade 列表
    """
    kline_index = _build_kline_index(klines_by_symbol)
    all_dates = _all_dates(signals_by_date, kline_index, window_end)

    cash = config.total_capital_usdt
    open_positions: list[OpenPosition] = []
    trades: list[BacktestTrade] = []

    for current_date in all_dates:
        # 1. 平仓检查（先平仓释放资金，当天才能复用）
        still_open: list[OpenPosition] = []
        for pos in open_positions:
            kline = kline_index.get(pos.symbol, {}).get(current_date)
            if kline is None:
                # 当日无 K 线（可能已下架且无数据），保留仓位待后续处理
                still_open.append(pos)
                continue

            outcome = _check_position_on_day(
                entry_price=pos.entry_price, tp_pct=pos.tp_pct, kline=kline,
                kline_date=current_date,
                delisting_date=delisting_by_symbol.get(pos.symbol),
            )
            if outcome == "win":
                cash += config.position_size_usdt  # 本金回流
                trades.append(BacktestTrade(
                    symbol=pos.symbol, entry_date=pos.entry_date,
                    entry_price=pos.entry_price, exit_date=current_date,
                    exit_price=pos.entry_price * (1.0 + pos.tp_pct),
                    outcome="win", tp_pct=pos.tp_pct,
                    pnl_usdt=config.position_size_usdt * pos.tp_pct,
                    hold_days=(current_date - pos.entry_date).days, realized=True,
                ))
            elif outcome == "loss":
                # 下架：资金不回流，亏损计入
                exit_price = kline.close_price_float
                trades.append(BacktestTrade(
                    symbol=pos.symbol, entry_date=pos.entry_date,
                    entry_price=pos.entry_price, exit_date=current_date,
                    exit_price=exit_price, outcome="loss", tp_pct=pos.tp_pct,
                    pnl_usdt=config.position_size_usdt * (exit_price / pos.entry_price - 1.0),
                    hold_days=(current_date - pos.entry_date).days, realized=True,
                ))
            else:
                still_open.append(pos)
        open_positions = still_open

        # 2. 开仓检查（当天有信号且资金/仓位允许）
        for signal in signals_by_date.get(current_date, []):
            if cash < config.position_size_usdt:
                break  # 资金不足，停止开仓
            if len(open_positions) >= config.max_positions:
                break  # 持仓满，停止开仓
            open_positions.append(OpenPosition(
                symbol=signal.symbol, entry_date=current_date,
                entry_price=signal.entry_price, tp_pct=tp_pct,
            ))
            cash -= config.position_size_usdt

    # 3. 窗口结束：剩余未平仓仓位按 final_price 结算
    for pos in open_positions:
        sym_klines = kline_index.get(pos.symbol, {})
        # 取窗口内最后可用 K 线的收盘价作为 final_price
        final_kline = None
        for d in reversed(all_dates):
            if d <= window_end and d in sym_klines:
                final_kline = sym_klines[d]
                break
        final_price = final_kline.close_price_float if final_kline else pos.entry_price
        unrealized = config.position_size_usdt * (final_price / pos.entry_price - 1.0)
        trades.append(BacktestTrade(
            symbol=pos.symbol, entry_date=pos.entry_date,
            entry_price=pos.entry_price, exit_date=None, exit_price=final_price,
            outcome="open", tp_pct=pos.tp_pct, pnl_usdt=unrealized,
            hold_days=(all_dates[-1] - pos.entry_date).days if all_dates else 0,
            realized=False,
        ))

    return trades
