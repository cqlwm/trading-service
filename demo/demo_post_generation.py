#!/usr/bin/env python3
"""端到端贴文生成演示：用构造的交易故事线调用真实 LLM 生成贴文。

不依赖真实交易，用 InMemoryTradingRepository 构造假的动作记录，
调用 PostGenerator + 真实 LLM 生成贴文，保存到 mydata/posts/。

运行：
    uv run python demo/demo_post_generation.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_service.config import settings
from trading_service.content.post_generator import PostGenerator, create_openai_client
from trading_service.repository.abc import (
    PositionRecord,
    StrategyActionRecord,
    TradingRepository,
)


class InMemoryRepo(TradingRepository):
    """极简内存仓库，仅供 demo 脚本使用。只实现贴文生成用到的方法。"""

    def __init__(self) -> None:
        self._positions: list[PositionRecord] = []
        self._actions: list[StrategyActionRecord] = []

    # --- 贴文生成用到的方法 ---

    def save_position(self, position: PositionRecord) -> None:
        self._positions.append(position)

    def list_positions(self, symbol=None, status=None, tag=None):
        return [
            p for p in self._positions
            if (symbol is None or p.symbol == symbol)
            and (status is None or p.status == status)
            and (tag is None or p.tag == tag)
        ]

    def get_positions(self, symbol=None, status=None, tag=None):
        return self.list_positions(symbol, status, tag)

    def count_positions(self, status=None, tag=None):
        return len(self.list_positions(status=status, tag=tag))

    def save_action(self, action: StrategyActionRecord) -> None:
        self._actions.append(action)

    def list_actions_by_execution(self, execution_id: str):
        return [a for a in self._actions if a.execution_id == execution_id]

    def list_actions_by_position(self, position_id: str):
        return [a for a in self._actions if a.position_id == position_id]

    def list_actions_by_symbol(self, symbol: str, limit: int = 50):
        return [a for a in self._actions if a.symbol == symbol][:limit]

    # --- 以下方法 demo 不用到，空实现满足接口 ---

    def get_position(self, position_id: str): pass  # type: ignore[override]
    def save_order(self, order): pass  # type: ignore[override]
    def list_orders(self, **kwargs): return []  # type: ignore[override]
    def get_orders_by_position(self, position_id: str): return []  # type: ignore[override]
    def count_orders(self, **kwargs): return 0  # type: ignore[override]
    def save_signal(self, signal): pass  # type: ignore[override]
    def list_signals(self, **kwargs): return []  # type: ignore[override]
    def count_signals(self, **kwargs): return 0  # type: ignore[override]
    def get_signals_filtered(self, **kwargs): return []  # type: ignore[override]
    def save_execution(self, execution): pass  # type: ignore[override]
    def list_executions(self, strategy_name: str, limit: int = 20, offset: int = 0): return []  # type: ignore[override]
    def save_schedule(self, schedule): pass  # type: ignore[override]
    def get_schedule(self, strategy_name: str): return None  # type: ignore[override]
    def list_schedules(self): return []  # type: ignore[override]
    def begin(self): pass  # type: ignore[override]
    def commit(self): pass  # type: ignore[override]
    def rollback(self): pass  # type: ignore[override]


def build_fake_story(repo) -> str:
    """构造一个完整的做空交易故事线，返回 execution_id。

    故事线：
    - 3小时前：开空仓 BTCUSDT @ 65000（涨幅榜 top1，超买信号）
    - 2小时前：第 1 次加仓 @ 65500（价格上涨触发安全单）
    - 1小时前：第 2 次加仓 @ 66000
    - 现在：止盈平仓 @ 63800（价格回落，获利平仓）
    """
    now = datetime.now(timezone.utc)
    execution_id = "demo_exec_001"
    symbol = "BTCUSDT"
    position_id = "demo_pos_001"
    strategy_name = "martingale_short"

    # 构造持仓记录（已平仓）
    repo.save_position(PositionRecord(
        id=position_id,
        symbol=symbol,
        direction="short",
        entry_price=65333.3,  # 加权均价
        total_size=350.0,  # 100 + 150 + 100
        status="closed",
        exit_price=63800.0,
        tag=strategy_name,
        created_at=now - timedelta(hours=3),
        closed_at=now,
    ))

    # 动作 1：开空仓
    repo.save_action(StrategyActionRecord(
        id="demo_act_001",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type="open",
        symbol=symbol,
        position_id=position_id,
        order_id="demo_ord_001",
        reason_text="开空仓 @ 65000.0",
        reason_data={
            "action": "initial_entry",
            "price": 65000.0,
            "size": 100.0,
        },
        created_at=now - timedelta(hours=3),
    ))

    # 动作 2：第 1 次加仓
    repo.save_action(StrategyActionRecord(
        id="demo_act_002",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type="add",
        symbol=symbol,
        position_id=position_id,
        order_id="demo_ord_002",
        reason_text="第 1 次加仓 @ 65500.0",
        reason_data={
            "action": "safety_order",
            "layer": 1,
            "price": 65500.0,
            "size": 150.0,
        },
        created_at=now - timedelta(hours=2),
    ))

    # 动作 3：第 2 次加仓
    repo.save_action(StrategyActionRecord(
        id="demo_act_003",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type="add",
        symbol=symbol,
        position_id=position_id,
        order_id="demo_ord_003",
        reason_text="第 2 次加仓 @ 66000.0",
        reason_data={
            "action": "safety_order",
            "layer": 2,
            "price": 66000.0,
            "size": 100.0,
        },
        created_at=now - timedelta(hours=1),
    ))

    # 动作 4：止盈平仓
    repo.save_action(StrategyActionRecord(
        id="demo_act_004",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type="close",
        symbol=symbol,
        position_id=position_id,
        order_id="demo_ord_004",
        reason_text="止盈平仓 @ 63800.0",
        reason_data={
            "action": "take_profit",
            "price": 63800.0,
            "profit_pct": 2.34,
        },
        created_at=now,
    ))

    return execution_id


def main() -> None:
    """构造假故事线，调用真实 LLM 生成贴文。"""
    repo = InMemoryRepo()
    execution_id = build_fake_story(repo)

    # 创建真实 LLM 客户端
    result = create_openai_client(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    if result is None:
        print("❌ LLM 未配置（llm_api_key 为空），请在 config.local.yaml 中配置")
        return

    llm_client, model = result
    gen = PostGenerator(
        repo=repo,
        posts_dir=settings.posts_dir,
        llm_client=llm_client,
        llm_model=model,
    )

    print(f"📝 调用 LLM 生成贴文 (model={model})...")
    print(f"   贴文保存目录: {settings.posts_dir}")
    print()

    files = gen.generate_for_execution(execution_id)

    if not files:
        print("❌ 未生成贴文（LLM 调用可能失败）")
        return

    for f in files:
        print(f"✅ 贴文已生成: {f}")
        print()
        print("=" * 60)
        print(f.read_text(encoding="utf-8"))
        print("=" * 60)


if __name__ == "__main__":
    main()
