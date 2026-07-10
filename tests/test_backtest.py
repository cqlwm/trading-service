"""测试回测核心逻辑（TDD 红阶段）。

simulate_trade: 模拟单笔"买入后持有"交易，判定止盈/下架/未决。
策略语义：无止损，止盈出场或持有到下架清算。
- win  = 价格触及 +TP% 止盈出场
- loss = 先到下架日，以下架日收盘价近似清算
- open = K 线用完仍未触发（窗口内未决）

二元盈亏结构：赢 +10×TP，输 ≈ -10×loss_pct（非精确 -100%）。

使用内存构造 K 线列表，零网络。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trading_service.clients import BinanceFutureKline
from trading_service.pickers.backtest import (
    BacktestResult,
    BacktestTrade,
    PortfolioConfig,
    SignalEntry,
    _check_position_on_day,
    scan_tp,
    simulate_portfolio,
    simulate_trade,
    summarize,
)


def make_kline(
    day_offset: int, open_p: float, high: float, low: float, close: float,
) -> BinanceFutureKline:
    """构造一根日 K 线，open_time = 基准日 + day_offset 天。"""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    open_time = int(base.timestamp() * 1000) + day_offset * 86_400_000
    close_time = open_time + 86_400_000 - 1
    return BinanceFutureKline(
        open_time=open_time, open_price=str(open_p), high_price=str(high),
        low_price=str(low), close_price=str(close), volume="100",
        close_time=close_time, quote_volume="0", trade_count=0,
        taker_buy_base_volume="0", taker_buy_quote_volume="0", ignore="0",
    )


class TestSimulateTradeWin:
    """止盈出场。"""

    def test_tp_hit_before_delist_is_win(self) -> None:
        """✅ 价格先达 TP -> win，exit_price=止盈价。"""
        # entry=100, TP=50% -> 止盈价 150。第3天 high=155 触及。
        klines = [
            make_kline(1, 100, 110, 95, 105),
            make_kline(2, 105, 120, 100, 115),
            make_kline(3, 115, 155, 110, 150),  # high 触及 150
        ]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=0.50,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.outcome == "win", f"应止盈出场，实际 {trade.outcome}"
        assert trade.exit_price == 150.0, f"止盈价应=150，实际 {trade.exit_price}"
        assert trade.hold_days == 3

    def test_tp_at_exact_high_is_win(self) -> None:
        """边界：high 恰好等于止盈价 -> win。"""
        # entry=100, TP=100% -> 止盈价 200。第2天 high 恰好 200。
        klines = [
            make_kline(1, 100, 130, 95, 120),
            make_kline(2, 120, 200, 115, 195),  # high 恰好 200
        ]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.outcome == "win"
        assert trade.exit_price == 200.0

    def test_win_pnl_calculation(self) -> None:
        """✅ 止盈 pnl = 10 × tp_pct（基于 10U 仓位）。"""
        klines = [make_kline(1, 100, 150, 95, 145)]  # TP=50% 当天触及
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=0.50,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.pnl_usdt == pytest.approx(5.0), f"50%止盈应赚5U，实际 {trade.pnl_usdt}"


class TestSimulateTradeLoss:
    """下架清算。"""

    def test_delist_before_tp_is_loss(self) -> None:
        """✅ 先到下架日 -> loss，exit_price=下架日收盘价。"""
        # entry=100, TP=100%。make_kline(2) 日期=1月3日=下架日。第2根收盘价 42 -> 清算。
        klines = [
            make_kline(1, 100, 110, 90, 95),  # 1月2日
            make_kline(2, 95, 100, 40, 42),   # 1月3日，下架
        ]
        delist = datetime(2026, 1, 3, tzinfo=timezone.utc)  # 对齐 make_kline(2) 日期
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=delist, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.outcome == "loss", f"应下架清算，实际 {trade.outcome}"
        assert trade.exit_price == 42.0, f"清算价应=下架日收盘42，实际 {trade.exit_price}"

    def test_loss_pnl_calculation(self) -> None:
        """✅ 下架 pnl = 10 × (exit/entry - 1)，非精确 -100%。"""
        # entry=100, 清算价=40 -> 亏 60% -> pnl = -6.0
        klines = [
            make_kline(1, 100, 110, 90, 95),
            make_kline(2, 95, 100, 40, 40),
        ]
        delist = datetime(2026, 1, 3, tzinfo=timezone.utc)  # 对齐 make_kline(2)
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=delist, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.pnl_usdt == pytest.approx(-6.0), f"清算40应亏6U，实际 {trade.pnl_usdt}"

    def test_delist_day_still_checks_tp_first(self) -> None:
        """优先级：下架当天若同时触及止盈，止盈优先（当天 high 先判）。"""
        # entry=100, TP=100% -> 止盈200。下架日=1月3日(make_kline(2))。当天 high=250 触及止盈。
        klines = [
            make_kline(1, 100, 110, 90, 105),
            make_kline(2, 105, 250, 100, 200),  # 下架日但 high 触及止盈
        ]
        delist = datetime(2026, 1, 3, tzinfo=timezone.utc)
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=delist, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.outcome == "win", "下架当天触及止盈应判 win"


class TestSimulateTradeOpen:
    """未决。"""

    def test_no_tp_no_delist_is_open(self) -> None:
        """✅ K 线用完仍未触发 -> open。"""
        klines = [
            make_kline(1, 100, 110, 95, 105),
            make_kline(2, 105, 115, 100, 110),
        ]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            final_price=110.0,
        )
        assert trade.outcome == "open", f"应未决，实际 {trade.outcome}"
        assert trade.exit_price == 110.0, "未决 exit_price 应=final_price"
        assert trade.realized is False

    def test_empty_klines_is_open(self) -> None:
        """空值：无买入后 K 线 -> open。"""
        trade = simulate_trade(
            klines=[], entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            final_price=100.0,
        )
        assert trade.outcome == "open"

    def test_open_pnl_uses_final_price(self) -> None:
        """✅ 未决仓位 pnl 按 final_price 结算未实现盈亏。

        entry=100, final=130 -> 未实现 +30% -> pnl = +3.0（10U 仓位）
        """
        klines = [
            make_kline(1, 100, 110, 95, 105),
            make_kline(2, 105, 115, 100, 110),
        ]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            final_price=130.0,
        )
        assert trade.outcome == "open"
        assert trade.pnl_usdt == pytest.approx(3.0), f"未决应按final算+3U，实际 {trade.pnl_usdt}"
        assert trade.realized is False

    def test_open_final_below_entry_is_negative(self) -> None:
        """✅ 未决且 final < entry -> 未实现亏损。"""
        klines = [make_kline(1, 100, 105, 80, 90)]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            final_price=70.0,
        )
        assert trade.outcome == "open"
        assert trade.pnl_usdt == pytest.approx(-3.0), f"final=70应亏3U，实际 {trade.pnl_usdt}"

    def test_open_without_final_price_zero_pnl(self) -> None:
        """兼容：未传 final_price -> 未决 pnl=0（旧契约兼容）。"""
        klines = [make_kline(1, 100, 105, 95, 102)]
        trade = simulate_trade(
            klines=klines, entry_price=100.0, tp_pct=1.0,
            delisting_date=None, symbol="ABCUSDT",
            entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert trade.outcome == "open"
        assert trade.pnl_usdt == 0.0


class TestSummarize:
    """汇总统计。"""

    def test_summarize_win_rate(self) -> None:
        """✅ 胜率 = wins / (wins + losses)，open 不计入分母。"""
        trades = [
            BacktestTrade(
                symbol="A", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=150.0,
                outcome="win", tp_pct=0.5, pnl_usdt=5.0, hold_days=3, realized=True,
            ),
            BacktestTrade(
                symbol="B", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=40.0,
                outcome="loss", tp_pct=0.5, pnl_usdt=-6.0, hold_days=10, realized=True,
            ),
            BacktestTrade(
                symbol="C", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=130.0,
                outcome="open", tp_pct=0.5, pnl_usdt=3.0, hold_days=20, realized=False,
            ),
        ]
        result = summarize(trades, tp_pct=0.5)
        assert result.wins == 1
        assert result.losses == 1
        assert result.open_trades == 1
        assert result.win_rate == 0.5, f"胜率应=50%，实际 {result.win_rate}"
        assert result.realized_pnl_usdt == pytest.approx(-1.0), "已实现=5-6=-1"
        assert result.unrealized_pnl_usdt == pytest.approx(3.0), "未实现=3"
        assert result.total_pnl_usdt == pytest.approx(2.0), "总盈亏=-1+3=2"

    def test_summarize_excludes_open_from_winrate(self) -> None:
        """✅ open 不计入胜率分母：2win+1open -> 胜率 100%。"""
        trades = [
            BacktestTrade(
                symbol="A", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=200.0,
                outcome="win", tp_pct=1.0, pnl_usdt=10.0, hold_days=3, realized=True,
            ),
            BacktestTrade(
                symbol="B", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=110.0,
                outcome="open", tp_pct=1.0, pnl_usdt=1.0, hold_days=20, realized=False,
            ),
        ]
        result = summarize(trades, tp_pct=1.0)
        assert result.win_rate == 1.0, f"open不计入分母，胜率应100%，实际 {result.win_rate}"

    def test_summarize_empty_trades(self) -> None:
        """空值：无交易 -> 胜率 0，总数 0。"""
        result = summarize([], tp_pct=0.5)
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.total_pnl_usdt == 0.0
        assert result.realized_pnl_usdt == 0.0
        assert result.unrealized_pnl_usdt == 0.0


class TestScanTp:
    """多 TP 扫描。"""

    def test_scan_tp_sorted_by_tp(self) -> None:
        """✅ scan_tp 按 TP 升序返回，即使输入乱序。"""
        trades_50 = [
            BacktestTrade(
                symbol="A", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=150.0,
                outcome="win", tp_pct=0.5, pnl_usdt=5.0, hold_days=3, realized=True,
            ),
        ]
        trades_200 = [
            BacktestTrade(
                symbol="A", entry_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                entry_price=100.0, exit_date=None, exit_price=20.0,
                outcome="loss", tp_pct=2.0, pnl_usdt=-8.0, hold_days=30, realized=True,
            ),
        ]
        # 故意乱序输入
        trades_by_tp = {2.0: trades_200, 0.5: trades_50}
        results = scan_tp(trades_by_tp)
        assert [r.tp_pct for r in results] == [0.5, 2.0]
        assert results[0].wins == 1
        assert results[1].losses == 1

    def test_scan_tp_returns_backtest_result_type(self) -> None:
        """✅ scan_tp 返回 BacktestResult 列表。"""
        results = scan_tp({})
        assert isinstance(results, list)
        assert all(isinstance(r, BacktestResult) for r in results)


# 基准日：所有 make_kline 的 day_offset 相对此日
_BASE_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _date(offset: int) -> datetime:
    """基准日 + offset 天。"""
    return _BASE_DATE + timedelta(days=offset)


class TestCheckPositionOnDay:
    """单笔仓位在某日是否触发止盈/下架的判定（共享原语）。"""

    def test_check_win_when_high_hits_tp(self) -> None:
        """✅ 当日 high 触及止盈价 -> 'win'。"""
        # entry=100, TP=50% -> 止盈价 150。当日 high=155 触及。
        kline = make_kline(1, 100, 155, 95, 145)
        result = _check_position_on_day(
            entry_price=100.0, tp_pct=0.5, kline=kline,
            kline_date=_date(1), delisting_date=None,
        )
        assert result == "win"

    def test_check_loss_when_delist_day(self) -> None:
        """✅ 当日为下架日 -> 'loss'。"""
        kline = make_kline(1, 100, 110, 40, 42)
        result = _check_position_on_day(
            entry_price=100.0, tp_pct=1.0, kline=kline,
            kline_date=_date(1), delisting_date=_date(1),
        )
        assert result == "loss"

    def test_check_none_when_no_trigger(self) -> None:
        """✅ 未触发止盈也未到下架日 -> None。"""
        kline = make_kline(1, 100, 110, 95, 105)
        result = _check_position_on_day(
            entry_price=100.0, tp_pct=1.0, kline=kline,
            kline_date=_date(1), delisting_date=None,
        )
        assert result is None

    def test_check_tp_priority_over_delist(self) -> None:
        """优先级：当日同时触及止盈+下架日 -> 'win'（止盈优先）。"""
        # entry=100, TP=100% -> 止盈价 200。当日 high=250 触及，同时是下架日。
        kline = make_kline(1, 100, 250, 100, 200)
        result = _check_position_on_day(
            entry_price=100.0, tp_pct=1.0, kline=kline,
            kline_date=_date(1), delisting_date=_date(1),
        )
        assert result == "win"


class TestSimulatePortfolioBasic:
    """simulate_portfolio 资金约束基础场景。"""

    def test_portfolio_opens_when_signal_and_cash_available(self) -> None:
        """✅ 有信号 + 有资金 -> 开仓。"""
        # 1月1日 ABC 有信号，entry_price=100。K线：1月2日触及50%止盈。
        signals = {_date(0): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)]}
        klines = {"ABCUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 155, 95, 145)]}
        delisting: dict[str, datetime | None] = {"ABCUSDT": None}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=0.5,
            config=PortfolioConfig(), window_end=_date(2),
        )
        assert len(trades) == 1
        assert trades[0].outcome == "win", f"应止盈，实际 {trades[0].outcome}"

    def test_portfolio_no_open_when_cash_insufficient(self) -> None:
        """边界：资金不足 -> 不开仓。

        10 个代币同时有信号，但只有 100U（10笔），第 11 个不该开仓。
        用 max_positions=100 放开仓位上限，只测资金约束。
        """
        signals_list = [SignalEntry(symbol=f"S{i}USDT", entry_price=100.0) for i in range(11)]
        signals = {_date(0): signals_list}
        klines = {f"S{i}USDT": [make_kline(0, 100, 100, 100, 100)] for i in range(11)}
        delisting: dict[str, datetime | None] = {f"S{i}USDT": None for i in range(11)}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=1.0,
            config=PortfolioConfig(total_capital_usdt=100.0, max_positions=100),
            window_end=_date(1),
        )
        # 100U / 10U = 最多 10 笔，第 11 个被资金约束拒掉
        assert len(trades) == 10, f"资金只够 10 笔，实际 {len(trades)}"

    def test_portfolio_no_open_when_max_positions_reached(self) -> None:
        """边界：持仓数达上限 -> 不开仓。

        11 个代币同时有信号，资金充足（1000U），但 max_positions=10。
        """
        signals_list = [SignalEntry(symbol=f"S{i}USDT", entry_price=100.0) for i in range(11)]
        signals = {_date(0): signals_list}
        klines = {f"S{i}USDT": [make_kline(0, 100, 100, 100, 100)] for i in range(11)}
        delisting: dict[str, datetime | None] = {f"S{i}USDT": None for i in range(11)}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=1.0,
            config=PortfolioConfig(total_capital_usdt=1000.0, max_positions=10),
            window_end=_date(1),
        )
        assert len(trades) == 10, f"持仓上限 10，实际 {len(trades)}"


class TestSimulatePortfolioCashFlow:
    """资金流转：止盈释放资金可复用，下架不释放。"""

    def test_portfolio_tp_releases_cash_for_reuse(self) -> None:
        """✅ 止盈释放资金 -> 同一天可开新仓。

        1月1日：ABC 有信号买入(占10U，剩90U)。无法再买第10个以后的。
        但更精确的测试：1月1日 ABC 买入，1月2日 ABC 止盈释放 10U，
        1月2日 DEF 有信号 -> 可以用释放的 10U 买入 DEF。
        用 max_positions=1 确保只有释放后才能开第二个。
        """
        signals = {
            _date(0): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)],
            _date(1): [SignalEntry(symbol="DEFUSDT", entry_price=100.0)],
        }
        # ABC: 1月1日买入100，1月2日 high=150 触及50%止盈
        # DEF: 1月2日买入100，窗口结束未平仓
        klines = {
            "ABCUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 150, 95, 145)],
            "DEFUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 110, 95, 105)],
        }
        delisting: dict[str, datetime | None] = {"ABCUSDT": None, "DEFUSDT": None}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=0.5,
            config=PortfolioConfig(total_capital_usdt=10.0, max_positions=1),
            window_end=_date(2),
        )
        # ABC 止盈 + DEF 开仓 = 2 笔
        symbols = {t.symbol for t in trades}
        assert "ABCUSDT" in symbols, "ABC 应开仓"
        assert "DEFUSDT" in symbols, "ABC 止盈释放资金后 DEF 应能开仓"

    def test_portfolio_delist_does_not_release_cash(self) -> None:
        """✅ 下架不释放资金 -> 无法开新仓。

        1月1日：ABC 买入(占10U，总资金仅10U)。
        1月2日：ABC 下架(资金不回流)，DEF 有信号 -> 无资金开仓。
        """
        signals = {
            _date(0): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)],
            _date(1): [SignalEntry(symbol="DEFUSDT", entry_price=100.0)],
        }
        # ABC: 1月2日下架，收盘40
        klines = {
            "ABCUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 95, 100, 40, 42)],
            "DEFUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 110, 95, 105)],
        }
        delisting: dict[str, datetime | None] = {"ABCUSDT": _date(1), "DEFUSDT": None}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=1.0,
            config=PortfolioConfig(total_capital_usdt=10.0, max_positions=10),
            window_end=_date(2),
        )
        symbols = {t.symbol for t in trades}
        assert "ABCUSDT" in symbols, "ABC 应开仓"
        assert "DEFUSDT" not in symbols, "ABC 下架不释放资金，DEF 不应开仓"

    def test_portfolio_same_symbol_can_stack(self) -> None:
        """✅ 同一代币可叠加加仓：两个不同日有信号 -> 两笔独立仓位。"""
        signals = {
            _date(0): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)],
            _date(1): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)],
        }
        klines = {"ABCUSDT": [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 100, 100, 100)]}
        delisting: dict[str, datetime | None] = {"ABCUSDT": None}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=1.0,
            config=PortfolioConfig(total_capital_usdt=100.0, max_positions=10),
            window_end=_date(2),
        )
        abc_trades = [t for t in trades if t.symbol == "ABCUSDT"]
        assert len(abc_trades) == 2, f"应叠加 2 笔，实际 {len(abc_trades)}"


class TestSimulatePortfolioEndOfDay:
    """窗口结束：未平仓仓位按 final_price 结算。"""

    def test_portfolio_open_positions_marked_to_market_at_end(self) -> None:
        """✅ 窗口结束未平仓 -> 按 final_price 结算未实现盈亏。"""
        # ABC 1月1日买入100，TP=100%。窗口内未触及200也未下架。
        # 窗口结束 final_price=130 -> 未实现 +30% -> +3U
        signals = {_date(0): [SignalEntry(symbol="ABCUSDT", entry_price=100.0)]}
        klines = {"ABCUSDT": [make_kline(0, 100, 110, 95, 105), make_kline(1, 105, 130, 100, 130)]}
        delisting: dict[str, datetime | None] = {"ABCUSDT": None}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=1.0,
            config=PortfolioConfig(), window_end=_date(2),
        )
        assert len(trades) == 1
        t = trades[0]
        assert t.outcome == "open"
        assert t.realized is False
        assert t.pnl_usdt == pytest.approx(3.0), f"final=130应+3U，实际 {t.pnl_usdt}"
        assert t.exit_price == 130.0

    def test_portfolio_respects_time_ordering(self) -> None:
        """组合：时间顺序正确 -- 多日多币，止盈释放后复用。

        1月1日：ABC 买入(100U总，占10剩90)
        1月1日：BCD 买入(占10剩80)... 共买10个(满仓满资金)
        1月2日：ABC 止盈释放10U -> 第11个 ZZZ 可买
        验证 ZZZ 出现在结果中。
        """
        day0_signals = [SignalEntry(symbol=f"S{i}USDT", entry_price=100.0) for i in range(10)]
        day0_signals.append(SignalEntry(symbol="ZZZUSDT", entry_price=100.0))  # 第11个，1月1日买不了
        signals = {
            _date(0): day0_signals,
        }
        # S0 在1月2日止盈(TP=50%, high=155)；其他都不触发；ZZZ 1月1日无资金买不了
        # 但 ZZZ 1月1日的信号在 S0 止盈前就该被拒（同日先平仓后开仓）
        # 为测"释放后复用"，让 ZZZ 信号在1月2日
        signals = {
            _date(0): [SignalEntry(symbol=f"S{i}USDT", entry_price=100.0) for i in range(10)],
            _date(1): [SignalEntry(symbol="ZZZUSDT", entry_price=100.0)],
        }
        # S0: 1月2日 high=155 触及50%止盈；其余 S1-S9 不触发；ZZZ 1月2日买入
        klines = {}
        for i in range(10):
            sym = f"S{i}USDT"
            if i == 0:
                klines[sym] = [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 155, 95, 145)]
            else:
                klines[sym] = [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 110, 95, 105)]
        klines["ZZZUSDT"] = [make_kline(0, 100, 100, 100, 100), make_kline(1, 100, 110, 95, 105)]
        delisting: dict[str, datetime | None] = {sym: None for sym in klines}

        trades = simulate_portfolio(
            signals_by_date=signals, klines_by_symbol=klines,
            delisting_by_symbol=delisting, tp_pct=0.5,
            config=PortfolioConfig(total_capital_usdt=100.0, max_positions=10),
            window_end=_date(2),
        )
        symbols = {t.symbol for t in trades}
        assert "S0USDT" in symbols
        assert "ZZZUSDT" in symbols, "S0止盈释放资金后，ZZZ应能开仓"
