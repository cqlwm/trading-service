"""交易贴文生成器：从交易故事线生成社交媒体贴文。

策略执行完成后，收集本次执行的动作记录、该币种的完整交易故事线、
历史贴文和当前持仓，全部作为上下文提交给 LLM，由 LLM 自行选择素材生成贴文。
贴文以时间戳命名，保存为 markdown 文件。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import openai

from trading_service.repository import TradingRepository
from trading_service.repository.abc import StrategyActionRecord

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """LLM 客户端协议：只需 chat.completions.create。"""

    def chat_completions_create(
        self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
    ) -> str:
        """调用 LLM 生成文本，返回回复内容。"""
        ...


class PostGenerator:
    """交易贴文生成器：从交易故事线生成社交媒体贴文。"""

    def __init__(
        self,
        repo: TradingRepository,
        posts_dir: str,
        llm_client: LLMClient | None = None,
        llm_model: str = "gpt-4o-mini",
    ) -> None:
        self._repo = repo
        self._posts_dir = Path(posts_dir)
        self._llm_client = llm_client
        self._llm_model = llm_model

    def generate_for_execution(self, execution_id: str) -> list[Path]:
        """为一次策略执行生成贴文。无 LLM 或无动作时返回空列表。"""
        if self._llm_client is None:
            return []

        actions = self._repo.list_actions_by_execution(execution_id)
        if not actions:
            return []

        symbols = {a.symbol for a in actions if a.symbol}
        saved_files: list[Path] = []
        for symbol in sorted(symbols):
            path = self._generate_for_symbol(symbol, actions, execution_id)
            if path is not None:
                saved_files.append(path)
        return saved_files

    def _generate_for_symbol(
        self, symbol: str, all_actions: list[StrategyActionRecord], execution_id: str,
    ) -> Path | None:
        """为单个 symbol 生成贴文。"""
        current_actions = [a for a in all_actions if a.symbol == symbol]
        context = self._build_context(symbol, current_actions, execution_id)
        prompt = self._build_prompt(context)
        post_text = self._call_llm(prompt)
        if not post_text:
            return None
        return self._save_post(symbol, post_text, current_actions, execution_id)

    def _build_context(
        self, symbol: str, current_actions: list[StrategyActionRecord], execution_id: str,
    ) -> dict[str, Any]:
        """收集全部上下文，交给 LLM 让它自己选素材。"""
        full_story = self._repo.list_actions_by_symbol(symbol)
        historical_posts = self._load_historical_posts(symbol)
        open_positions = [
            self._position_summary(p)
            for p in self._repo.list_positions(symbol=symbol, status="open")
        ]

        return {
            "symbol": symbol,
            "execution_id": execution_id,
            "strategy_name": current_actions[0].strategy_name if current_actions else "",
            "current_actions": [self._action_summary(a) for a in current_actions],
            "full_story": [self._action_summary(a) for a in full_story],
            "historical_posts": historical_posts,
            "open_positions": open_positions,
        }

    def _build_prompt(self, context: dict[str, Any]) -> str:
        """构建 prompt：把全部上下文以结构化文本呈现，让 LLM 自行选择素材。"""
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
{self._format_historical_posts(context["historical_posts"])}

### 当前持仓
{json.dumps(context["open_positions"], ensure_ascii=False, indent=2)}

## 输出要求
- 只输出贴文正文，不要加标题或解释
- 如果历史贴文已提到过某个动作（如开仓），不要重复叙述，可以从新角度切入
- 中文输出
"""

    def _call_llm(self, prompt: str) -> str | None:
        """调用 LLM 生成贴文。client 为 None 或调用失败时返回 None。"""
        if self._llm_client is None:
            return None
        try:
            return self._llm_client.chat_completions_create(
                model=self._llm_model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    def _save_post(
        self, symbol: str, post_text: str,
        actions: list[StrategyActionRecord], execution_id: str,
    ) -> Path:
        """保存贴文到文件。文件名: {timestamp}_{symbol}.md"""
        now = datetime.now(timezone.utc)
        filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{symbol}.md"
        filepath = self._posts_dir / filename

        strategy_name = actions[0].strategy_name if actions else ""
        actions_text = "\n".join(
            f"- {a.action_type} @ {a.reason_text} (data: {json.dumps(a.reason_data, ensure_ascii=False)})"
            for a in actions
        )

        content = f"""# {symbol} 交易贴文

**生成时间**: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC
**执行轮次**: {execution_id}
**策略**: {strategy_name}

---

{post_text}

---

## 附：本次执行动作

{actions_text}
"""
        self._posts_dir.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"贴文已保存: {filepath}")
        return filepath

    def _load_historical_posts(self, symbol: str) -> list[str]:
        """读取该 symbol 的历史贴文正文。"""
        if not self._posts_dir.exists():
            return []

        posts: list[str] = []
        for filepath in sorted(self._posts_dir.glob(f"*_{symbol}.md")):
            text = filepath.read_text(encoding="utf-8")
            body = self._extract_post_body(text)
            if body:
                posts.append(body)
        return posts

    @staticmethod
    def _extract_post_body(text: str) -> str:
        """从贴文文件中提取正文（两个 --- 之间的内容）。"""
        parts = text.split("---")
        if len(parts) >= 3:
            return parts[1].strip()
        return ""

    @staticmethod
    def _action_summary(a: StrategyActionRecord) -> dict[str, Any]:
        """将动作记录转为简洁的字典。"""
        return {
            "action": a.action_type,
            "symbol": a.symbol,
            "reason": a.reason_text,
            "data": a.reason_data,
            "time": a.created_at.isoformat(),
        }

    @staticmethod
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

    @staticmethod
    def _format_historical_posts(posts: list[str]) -> str:
        """格式化历史贴文列表。"""
        if not posts:
            return "（暂无历史贴文）"
        return "\n\n---\n\n".join(
            f"### 历史贴文 #{i + 1}\n{post}" for i, post in enumerate(posts)
        )


def create_openai_client(base_url: str, api_key: str, model: str) -> tuple[LLMClient, str] | None:
    """创建 OpenAI 兼容客户端。api_key 为空时返回 None。"""
    if not api_key:
        return None

    client = openai.OpenAI(base_url=base_url, api_key=api_key)

    class _Adapter:
        """适配 openai SDK 到 LLMClient 协议。"""

        def chat_completions_create(
            self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
        ) -> str:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],  # type: ignore[list-item]
                temperature=temperature,
            )
            content = resp.choices[0].message.content
            return content if content is not None else ""

    return _Adapter(), model
