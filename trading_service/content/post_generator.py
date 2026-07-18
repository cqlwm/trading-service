"""贴文生成器接口与实现。

IPostGenerator 定义贴文生成的唯一契约 generate_for_execution。
PostGenerator 是默认实现，按 action_type 分发到不同的 PostStyle，
共享 LLM 调用、文件保存、历史贴文加载等基础设施。

生成贴文后可选自动发布到 Binance Square（通过 IPublisher），
发布结果回写到 PostRecord 的 published_at / share_link / publish_error 字段。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from trading_service.content.llm_client import LLMClient
from trading_service.content.publisher import IPublisher, resolve_base_asset
from trading_service.content.styles import ContentPostStyle, PostStyle, TradingPostStyle
from trading_service.repository import TradingRepository
from trading_service.repository.abc import PostRecord, StrategyActionRecord

logger = logging.getLogger(__name__)


class IPostGenerator(ABC):
    """贴文生成器接口。"""

    @abstractmethod
    async def generate_for_execution(self, execution_id: str) -> list[Path]:
        """为一次策略执行生成贴文。"""
        ...


class PostGenerator(IPostGenerator):
    """贴文生成器：按 action_type 分发到不同 PostStyle。

    共享基础设施（LLM 调用、文件保存、历史贴文加载）在本类中，
    上下文构建和 prompt 构建委托给可插拔的 PostStyle。
    生成后可选通过 IPublisher 自动发布到 Binance Square。
    """

    def __init__(
        self,
        repo: TradingRepository,
        posts_dir: str,
        llm_client: LLMClient | None = None,
        llm_model: str = "gpt-4o-mini",
        styles: list[PostStyle] | None = None,
        publisher: IPublisher | None = None,
        publish_timeframe: str = "1h",
    ) -> None:
        self._repo = repo
        self._posts_dir = Path(posts_dir)
        self._llm_client = llm_client
        self._llm_model = llm_model
        self._publisher = publisher
        self._publish_timeframe = publish_timeframe

        # 注册风格：默认包含交易型和内容型
        self._styles: dict[str, PostStyle] = {}
        for style in (styles or [TradingPostStyle(), ContentPostStyle()]):
            self._styles[style.action_type] = style
        self._default_style_key = "trading"

    async def generate_for_execution(self, execution_id: str) -> list[Path]:
        """为一次策略执行生成贴文。无 LLM 或无动作时返回空列表。

        生成 + 发布均在后台线程中执行（LLM 和 Playwright 都是同步阻塞调用）。
        发布失败不影响贴文生成结果，仅记录 publish_error。
        """
        return await asyncio.to_thread(self._generate_for_execution_sync, execution_id)

    def _generate_for_execution_sync(self, execution_id: str) -> list[Path]:
        """同步执行：生成贴文 -> 保存 -> 可选发布 -> 回写结果。"""
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
        """用指定风格生成贴文，并可选发布。"""
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

        # 落库 PostRecord（prompt + post_text 与 execution_id 关联）
        post_id = self._save_post_record(
            symbol=symbol, prompt=prompt, post_text=post_text,
            actions=actions, execution_id=execution_id, style=style.action_type,
        )

        path = self._save_post(symbol, post_text, actions, execution_id)

        # 自动发布到 Binance Square（失败不抛出，仅记录错误）
        self._try_publish(post_id, symbol, post_text)

        return [path]

    def _try_publish(self, post_id: str, symbol: str, post_text: str) -> None:
        """入队发布到 Binance Square（异步管道，不阻塞）。

        发布结果由 publisher 全局回调异步回写 PostRecord
        （published_at/share_link/publish_error），本方法只负责入队。
        """
        if self._publisher is None:
            return
        base_asset = resolve_base_asset(symbol)
        self._publisher.enqueue(
            publish_id=post_id,
            base_asset=base_asset,
            content=post_text,
            timeframe=self._publish_timeframe,
        )
        logger.info(f"贴文 {post_id} 已入队 Binance Square 发布管道")

    def _save_post_record(
        self,
        symbol: str,
        prompt: str,
        post_text: str,
        actions: list[StrategyActionRecord],
        execution_id: str,
        style: str,
    ) -> str:
        """将贴文（含完整 prompt）落库到 trading_posts，返回 post_id。"""
        action = actions[0] if actions else None
        post_id = uuid.uuid4().hex[:12]
        record = PostRecord(
            id=post_id,
            execution_id=execution_id,
            action_type=action.action_type if action else "",
            symbol=symbol,
            strategy_name=action.strategy_name if action else "",
            style=style,
            prompt=prompt,
            post_text=post_text,
            created_at=datetime.now(timezone.utc),
        )
        self._repo.save_post(record)
        return post_id

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

    def _load_historical_posts(self, symbol: str) -> list[dict[str, str]]:
        """读取该 symbol 的历史贴文（含时间），用于 prompt 上下文去重。

        从数据库读取，返回 [{time, text}, ...]，按时间正序。
        """
        records = self._repo.list_posts_by_symbol(symbol)
        return [
            {"time": r.created_at.isoformat(), "text": r.post_text}
            for r in records
        ]
