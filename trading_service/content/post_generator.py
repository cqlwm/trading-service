"""贴文生成器接口与实现。

IPostGenerator 定义贴文生成的唯一契约 generate_for_execution。
PostGenerator 是默认实现，按 action_type 分发到不同的 PostStyle，
共享 LLM 调用、文件保存、历史贴文加载等基础设施。
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from trading_service.content.llm_client import LLMClient
from trading_service.content.styles import ContentPostStyle, PostStyle, TradingPostStyle
from trading_service.repository import TradingRepository
from trading_service.repository.abc import StrategyActionRecord

logger = logging.getLogger(__name__)


class IPostGenerator(ABC):
    """贴文生成器接口。"""

    @abstractmethod
    def generate_for_execution(self, execution_id: str) -> list[Path]:
        """为一次策略执行生成贴文。"""
        ...


class PostGenerator(IPostGenerator):
    """贴文生成器：按 action_type 分发到不同 PostStyle。

    共享基础设施（LLM 调用、文件保存、历史贴文加载）在本类中，
    上下文构建和 prompt 构建委托给可插拔的 PostStyle。
    """

    def __init__(
        self,
        repo: TradingRepository,
        posts_dir: str,
        llm_client: LLMClient | None = None,
        llm_model: str = "gpt-4o-mini",
        styles: list[PostStyle] | None = None,
    ) -> None:
        self._repo = repo
        self._posts_dir = Path(posts_dir)
        self._llm_client = llm_client
        self._llm_model = llm_model

        # 注册风格：默认包含交易型和内容型
        self._styles: dict[str, PostStyle] = {}
        for style in (styles or [TradingPostStyle(), ContentPostStyle()]):
            self._styles[style.action_type] = style
        self._default_style_key = "trading"

    def generate_for_execution(self, execution_id: str) -> list[Path]:
        """为一次策略执行生成贴文。无 LLM 或无动作时返回空列表。"""
        if self._llm_client is None:
            return []

        actions = self._repo.list_actions_by_execution(execution_id)
        if not actions:
            return []

        # 按 action_type 分组：content 走 content 风格，其他走 trading 风格
        content_actions = [a for a in actions if a.action_type == "content"]
        trading_actions = [a for a in actions if a.action_type != "content"]

        saved_files: list[Path] = []

        if content_actions:
            style = self._styles.get("content")
            if style:
                saved_files.extend(self._generate_with_style(style, content_actions, execution_id))

        if trading_actions:
            style = self._styles.get(self._default_style_key)
            if style:
                # 交易型按 symbol 分组
                symbols = {a.symbol for a in trading_actions if a.symbol}
                for symbol in sorted(symbols):
                    symbol_actions = [a for a in trading_actions if a.symbol == symbol]
                    saved_files.extend(self._generate_with_style(style, symbol_actions, execution_id))

        return saved_files

    def _generate_with_style(
        self, style: PostStyle, actions: list[StrategyActionRecord], execution_id: str,
    ) -> list[Path]:
        """用指定风格生成贴文。"""
        context = style.build_context(
            repo=self._repo,
            actions=actions,
            execution_id=execution_id,
            load_historical_posts=self._load_historical_posts,
        )
        prompt = style.build_prompt(context)
        post_text = self._call_llm(prompt)
        if not post_text:
            return []

        symbol = actions[0].symbol if actions else ""
        if not symbol:
            return []
        path = self._save_post(symbol, post_text, actions, execution_id)
        return [path]

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
