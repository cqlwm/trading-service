"""策略动作记录（StrategyActionRecord）测试。

验证动作记录的写入、关联查询和故事线功能。
"""
from __future__ import annotations

from trading_service.exchange import MockExchange
from trading_service.types import TradeDirection


class TestActionRecordWrite:
    """测试动作记录的写入。"""

    def test_open_position_writes_action_record(self, exchange: MockExchange) -> None:
        """开仓应写入 action_type="open" 的动作记录。"""
        position = exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="martingale",
            reason_text="开仓 @ 50000",
            reason_data={"action": "initial_entry"},
            execution_id="exec_001",
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 1
        assert actions[0].action_type == "open"
        assert actions[0].strategy_name == "martingale"
        assert actions[0].execution_id == "exec_001"
        assert actions[0].order_id != ""

    def test_add_position_writes_action_record(self, exchange: MockExchange) -> None:
        """加仓应写入 action_type="add" 的动作记录。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="开仓",
        )
        exchange.add_position(
            position_id=position.id,
            size=200,
            price=49000,
            reason_text="第 1 次加仓",
            reason_data={"action": "safety_order", "layer": 1},
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 2
        add_actions = [a for a in actions if a.action_type == "add"]
        assert len(add_actions) == 1
        assert add_actions[0].reason_data["layer"] == 1

    def test_close_position_writes_action_record(self, exchange: MockExchange) -> None:
        """平仓应写入 action_type="close" 的动作记录。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="开仓",
        )
        exchange.close_position(
            position_id=position.id,
            price=51000,
            reason_text="止盈平仓 @ 51000",
            reason_data={"action": "take_profit"},
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 2
        close_actions = [a for a in actions if a.action_type == "close"]
        assert len(close_actions) == 1
        assert close_actions[0].reason_text == "止盈平仓 @ 51000"


class TestActionRecordStory:
    """测试动作记录的故事线查询。"""

    def test_position_story_timeline(self, exchange: MockExchange) -> None:
        """按 position_id 查询应返回按时间正序的完整交易故事。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale",
            reason_text="开仓 @ 50000",
        )
        exchange.add_position(
            position_id=position.id, size=200, price=49000,
            reason_text="第 1 次加仓 @ 49000",
        )
        exchange.close_position(
            position_id=position.id, price=51000,
            reason_text="止盈平仓 @ 51000",
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 3
        # 时间正序：open -> add -> close
        assert actions[0].action_type == "open"
        assert actions[1].action_type == "add"
        assert actions[2].action_type == "close"

    def test_symbol_story_timeline(self, exchange: MockExchange) -> None:
        """按 symbol 查询应返回该币种所有仓位的动作记录。"""
        # 仓位 1
        pos1 = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="开仓 1",
        )
        exchange.close_position(
            position_id=pos1.id, price=51000, reason_text="平仓 1",
        )
        # 仓位 2（同 symbol）
        pos2 = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=52000, tag="martingale", reason_text="开仓 2",
        )
        exchange.close_position(
            position_id=pos2.id, price=53000, reason_text="平仓 2",
        )

        actions = exchange.db.list_actions_by_symbol("BTCUSDT")
        assert len(actions) == 4
        # 按时间正序
        assert actions[0].action_type == "open"
        assert actions[1].action_type == "close"
        assert actions[2].action_type == "open"
        assert actions[3].action_type == "close"

    def test_empty_position_returns_empty_list(self, exchange: MockExchange) -> None:
        """空仓位查询应返回空列表。"""
        actions = exchange.db.list_actions_by_position("nonexistent")
        assert len(actions) == 0

    def test_empty_symbol_returns_empty_list(self, exchange: MockExchange) -> None:
        """空 symbol 查询应返回空列表。"""
        actions = exchange.db.list_actions_by_symbol("NONEXISTENT")
        assert len(actions) == 0


class TestActionRecordIsolation:
    """测试动作记录的策略隔离。"""

    def test_tag_isolation_between_strategies(self, exchange: MockExchange) -> None:
        """不同策略的动作记录不应混淆。"""
        pos_martingale = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="马丁开仓",
        )
        pos_micro_cap = exchange.open_position(
            symbol="ETHUSDT", direction=TradeDirection.LONG,
            size=50, price=3000, tag="micro_cap", reason_text="微市值开仓",
        )

        martingale_actions = exchange.db.list_actions_by_position(pos_martingale.id)
        micro_cap_actions = exchange.db.list_actions_by_position(pos_micro_cap.id)

        assert len(martingale_actions) == 1
        assert martingale_actions[0].strategy_name == "martingale"
        assert len(micro_cap_actions) == 1
        assert micro_cap_actions[0].strategy_name == "micro_cap"


class TestActionRecordManual:
    """测试手动操作的动作记录。"""

    def test_manual_close_has_empty_execution_id(self, exchange: MockExchange) -> None:
        """手动平仓的动作记录 execution_id 应为空。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="开仓",
        )
        # 不传 execution_id，默认为空
        exchange.close_position(
            position_id=position.id,
            price=51000,
        )

        actions = exchange.db.list_actions_by_position(position.id)
        close_actions = [a for a in actions if a.action_type == "close"]
        assert len(close_actions) == 1
        assert close_actions[0].execution_id == ""


class TestActionRecordSignalIds:
    """测试动作记录的 signal_ids 字段。"""

    def test_open_with_signal_ids(self, exchange: MockExchange) -> None:
        """开仓时传入 signal_ids，动作记录应保存。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="micro_cap", reason_text="金叉开仓",
            signal_ids=["sig_001", "sig_002"],
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 1
        assert actions[0].signal_ids == ["sig_001", "sig_002"]

    def test_open_without_signal_ids_defaults_empty(self, exchange: MockExchange) -> None:
        """不传 signal_ids 时，默认为空列表。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="martingale", reason_text="开仓",
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 1
        assert actions[0].signal_ids == []

    def test_multiple_signals_one_action(self, exchange: MockExchange) -> None:
        """一个动作基于多个信号时，signal_ids 应包含所有信号 ID。"""
        position = exchange.open_position(
            symbol="BTCUSDT", direction=TradeDirection.LONG,
            size=100, price=50000, tag="micro_cap", reason_text="多信号开仓",
            signal_ids=["sig_golden", "sig_volume", "sig_momentum"],
        )

        actions = exchange.db.list_actions_by_position(position.id)
        assert len(actions) == 1
        assert len(actions[0].signal_ids) == 3
        assert "sig_golden" in actions[0].signal_ids
        assert "sig_volume" in actions[0].signal_ids
        assert "sig_momentum" in actions[0].signal_ids
