"""贴文风格：从动作记录构建上下文和 prompt。

PostStyle 是可插拔的策略对象，负责将动作记录转化为 LLM 可读的上下文和 prompt。
不同 action_type 对应不同风格：
- TradingPostStyle：交易型（open/add/close），交易故事线上下文 + 交易员角色
- ContentPostStyle：内容型（content），信号上下文 + 市场观察者角色

加新风格只需继承 PostStyle 并注册到 PostGenerator._styles。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from trading_service.repository import TradingRepository
from trading_service.repository.abc import StrategyActionRecord


def _action_summary(a: StrategyActionRecord) -> dict[str, Any]:
    """将动作记录转为简洁的字典。"""
    return {
        "action": a.action_type,
        "symbol": a.symbol,
        "reason": a.reason_text,
        "data": a.reason_data,
        "time": a.created_at.isoformat(),
    }


def _position_summary(p: Any) -> dict[str, Any]:
    """将持仓记录转为简洁的字典。"""
    return {
        "symbol": p.symbol,
        "direction": p.direction,
        "entry_price": p.entry_price,
        "total_size": p.total_size,
        "tag": p.tag,
        "created_at": p.created_at.isoformat(),
    }


def _format_historical_posts(posts: list[dict[str, str]]) -> str:
    """格式化历史贴文列表（含发布时间）。"""
    if not posts:
        return "（暂无历史贴文）"
    return "\n\n---\n\n".join(
        f"### 历史贴文 #{i + 1}（{p["time"]}）\n{p["text"]}" for i, p in enumerate(posts)
    )


class PostStyle(ABC):
    """贴文风格：负责从动作记录构建上下文和 prompt。"""

    @property
    @abstractmethod
    def action_type(self) -> str:
        """匹配的 action_type 标识（如 "content"、"trading"）。"""
        ...

    @abstractmethod
    def build_context(
        self,
        repo: TradingRepository,
        actions: list[StrategyActionRecord],
        execution_id: str,
        load_historical_posts: Any,
    ) -> dict[str, Any]:
        """从动作记录构建上下文。

        Args:
            repo: 数据仓库，用于拉取故事线/信号/持仓
            actions: 本次执行中该风格相关的动作记录
            execution_id: 执行轮次 ID
            load_historical_posts: 回调函数 (symbol) -> list[dict]，读取历史贴文（含 time/text）
        """
        ...

    @abstractmethod
    def build_prompt(self, context: dict[str, Any]) -> str:
        """构建 LLM prompt。"""
        ...


class TradingPostStyle(PostStyle):
    """交易型风格：交易故事线上下文 + 交易员角色。"""

    @property
    def action_type(self) -> str:
        return "trading"

    def build_context(
        self,
        repo: TradingRepository,
        actions: list[StrategyActionRecord],
        execution_id: str,
        load_historical_posts: Any,
    ) -> dict[str, Any]:
        """收集交易上下文：本次动作 + 完整故事线 + 历史贴文 + 持仓。"""
        symbol = actions[0].symbol if actions else ""
        full_story = repo.list_actions_by_symbol(symbol) if symbol else []
        historical_posts = load_historical_posts(symbol) if symbol else []
        open_positions = [
            _position_summary(p)
            for p in repo.list_positions(symbol=symbol, status="open")
        ] if symbol else []

        return {
            "symbol": symbol,
            "execution_id": execution_id,
            "strategy_name": actions[0].strategy_name if actions else "",
            "current_actions": [_action_summary(a) for a in actions],
            "full_story": [_action_summary(a) for a in full_story],
            "historical_posts": historical_posts,
            "open_positions": open_positions,
        }

    def build_prompt(self, context: dict[str, Any]) -> str:
        """交易型 prompt（马丁做空等策略）。"""
        return f"""你是一位加密货币交易员，负责为社交媒体撰写交易动态贴文。

## 你的角色
- 你在运行一个马丁格尔做空策略，从涨幅榜中寻找做空机会
- 贴文风格：专业但不失活泼，像交易员的日常分享
- 简短精炼（100-200字），适合社交媒体发布

## 当前交易上下文
以下是本次交易执行的完整上下文信息。请你自行判断哪些信息适合作为贴文素材，
不要简单罗列所有数据，而是提炼出有价值的交易叙事。

### 本次执行动作
{json.dumps(context["current_actions"], ensure_ascii=False, indent=2)}

### 该币种完整交易故事线（历史所有动作）
{json.dumps(context["full_story"], ensure_ascii=False, indent=2)}

### 该币种历史贴文（避免重复内容）
{_format_historical_posts(context["historical_posts"])}

### 当前持仓
{json.dumps(context["open_positions"], ensure_ascii=False, indent=2)}

## 输出要求
- 只输出贴文正文，不要加标题或解释
- 如果历史贴文已提到过某个动作（如开仓），不要重复叙述，可以从新角度切入
- 中文输出
"""


class ContentPostStyle(PostStyle):
    """内容型风格：市场快照上下文 + 市场观察者角色。

    上下文来源（优先级）：
    1. action.reason_data["market_snapshot"]（新路径，ContentScanStrategy 聚合的完整快照，
       聚焦当前 symbol 的多周期信号 + 实时价/时间/24h涨跌；走 reason_data 不依赖 list_signals 回读）
    2. 回退到 list_signals 反查 action.signal_ids（旧数据兼容）

    检测器自治：market_snapshot.signals[].metadata 是各检测器贡献的上下文，
    新检测器只需写好 SignalResult.metadata 即可自动进入 prompt，零改动扩展。
    """

    @property
    def action_type(self) -> str:
        return "content"

    def build_context(
        self,
        repo: TradingRepository,
        actions: list[StrategyActionRecord],
        execution_id: str,
        load_historical_posts: Any,
    ) -> dict[str, Any]:
        """收集内容上下文：市场快照 + 历史贴文。"""
        action = actions[0] if actions else None
        if action is None:
            return {
                "symbol": "",
                "execution_id": execution_id,
                "strategy_name": "",
                "current_actions": [],
                "market_snapshot": {"signals": []},
                "historical_posts": [],
            }

        historical_posts = load_historical_posts(action.symbol)

        # 优先用 reason_data.market_snapshot（新路径）；无则回退到 list_signals 反查（旧数据兼容）
        market_snapshot = action.reason_data.get("market_snapshot")
        if market_snapshot is None:
            market_snapshot = self._build_legacy_market_snapshot(repo, action)

        return {
            "symbol": action.symbol,
            "execution_id": execution_id,
            "strategy_name": action.strategy_name,
            "current_actions": [_action_summary(action)],
            "market_snapshot": market_snapshot,
            "historical_posts": historical_posts,
        }

    def _build_legacy_market_snapshot(
        self, repo: TradingRepository, action: StrategyActionRecord,
    ) -> dict[str, Any]:
        """旧数据兼容：reason_data 无 market_snapshot 时，从 list_signals 反查构建快照。

        旧 action 的 reason_data 只有 signal_ids，需回查信号表。
        SQL 路径下信号 metadata 会丢失运行时注入的字段（current_price/time），
        但旧数据本就没有这些字段，回退行为可接受。
        """
        signals: list[dict[str, Any]] = []
        for sid in action.signal_ids:
            sig_records = repo.list_signals(symbol=action.symbol, limit=20)
            for sr in sig_records:
                if sr.id == sid:
                    signals.append({
                        "signal_type": sr.signal_type,
                        "direction": sr.direction,
                        "severity": sr.severity,
                        "description": sr.description,
                        "interval": sr.metadata_json.get("interval"),
                        "metadata": sr.metadata_json,
                    })
        return {"signals": signals}

    def build_prompt(self, context: dict[str, Any]) -> str:
        """内容型 prompt（市场观察、趋势分析等）。"""
        return f"""你是一位加密货币市场观察者，负责为社交媒体撰写市场动态贴文。

## 你的角色
- 你在观察加密货币市场的价格趋势和K线形态，分享有趣的市场现象
- 贴文风格：专业但不失活泼，像交易员的日常观察分享
- 简短精炼（100-200字），适合社交媒体发布

## 当前观察上下文
以下是本次市场扫描的完整上下文信息。请你自行判断哪些信息适合作为贴文素材，
不要简单罗列所有数据，而是提炼出有价值的市场观察。

### 市场快照
{json.dumps(context["market_snapshot"], ensure_ascii=False, indent=2)}

### 该币种历史贴文（避免重复内容）
{_format_historical_posts(context["historical_posts"])}

## 输出要求
- 只输出贴文正文，不要加标题或解释
- 如果历史贴文已提到过某个现象，不要重复叙述，可以从新角度切入
- 中文输出
"""
