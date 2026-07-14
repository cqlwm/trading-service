"""测试 PostGenerator 交易贴文生成器。

测试覆盖：
1. 正常路径：有动作记录 -> 生成贴文 -> 保存文件
2. 空动作跳过：execution 无动作 -> 返回空列表
3. 无 LLM 跳过：client 为 None -> 返回空列表
4. 多 symbol 分组：一次 execution 涉及多个 symbol -> 每个生成一篇
5. 历史贴文去重：symbol 有历史贴文 -> 作为上下文传入 prompt
6. LLM 异常不崩溃：LLM 调用失败 -> 返回空列表
7. 文件命名：验证文件名格式 {timestamp}_{symbol}.md
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from trading_service.content.post_generator import PostGenerator
from trading_service.repository.abc import StrategyActionRecord


class FakeLLMClient:
    """内存版 LLM 客户端：记录 prompt，返回固定文本。"""

    def __init__(self, response: str = "这是一条测试贴文。", should_fail: bool = False) -> None:
        self._response = response
        self._should_fail = should_fail
        self.prompts: list[str] = []

    def chat_completions_create(
        self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
    ) -> str:
        if self._should_fail:
            raise RuntimeError("LLM 服务不可用")
        self.prompts.append(messages[0]["content"] if messages else "")
        return self._response


def make_action(
    symbol: str = "BTCUSDT",
    action_type: str = "open",
    execution_id: str = "exec001",
    strategy_name: str = "martingale_short",
    reason_text: str = "开仓 @ 65000",
    reason_data: dict | None = None,
) -> StrategyActionRecord:
    """构造一个动作记录。"""
    return StrategyActionRecord(
        id=f"act_{symbol}_{action_type}",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type=action_type,
        symbol=symbol,
        position_id="pos001",
        order_id="ord001",
        reason_text=reason_text,
        reason_data=reason_data or {"action": "initial_entry", "price": 65000},
        signal_ids=[],
    )


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def posts_dir(tmp_path: Path) -> Path:
    return tmp_path / "posts"


class TestPostGeneratorNormalPath:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_generates_post_and_saves_file(self, repo, posts_dir: Path) -> None:
        """✅ 有动作记录 -> 生成贴文 -> 保存文件。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 做空入场，目标明确！")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec001")

        assert len(files) == 1
        assert files[0].exists()
        content = files[0].read_text(encoding="utf-8")
        assert "BTC 做空入场，目标明确！" in content
        assert "BTCUSDT" in content

    @pytest.mark.asyncio
    async def test_file_naming_format(self, repo, posts_dir: Path) -> None:
        """✅ 文件名格式: {timestamp}_{symbol}.md"""
        repo.save_action(make_action(symbol="ETHUSDT"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec001")

        assert len(files) == 1
        filename = files[0].name
        assert filename.endswith("_ETHUSDT.md"), f"文件名应以 _ETHUSDT.md 结尾，实际: {filename}"
        # 验证时间戳格式 YYYY-MM-DD_HHMMSS
        prefix = filename[:-len("_ETHUSDT.md")]
        datetime.strptime(prefix, "%Y-%m-%d_%H%M%S")

    @pytest.mark.asyncio
    async def test_post_includes_action_metadata(self, repo, posts_dir: Path) -> None:
        """✅ 贴文文件底部应附本次执行动作记录。"""
        repo.save_action(make_action(
            symbol="BTCUSDT", action_type="add",
            reason_text="第 1 次加仓 @ 65500",
            reason_data={"action": "safety_order", "layer": 1},
        ))
        llm = FakeLLMClient(response="贴文正文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec001")

        content = files[0].read_text(encoding="utf-8")
        assert "第 1 次加仓 @ 65500" in content
        assert "safety_order" in content


class TestPostGeneratorSkipConditions:
    """跳过条件测试。"""

    @pytest.mark.asyncio
    async def test_empty_actions_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ execution 无动作 -> 返回空列表，不调 LLM。"""
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("nonexistent_exec")

        assert files == []
        assert len(llm.prompts) == 0, "无动作时不应调用 LLM"

    @pytest.mark.asyncio
    async def test_no_llm_client_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ client 为 None -> 返回空列表。"""
        repo.save_action(make_action())
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=None)

        files = await gen.generate_for_execution("exec001")

        assert files == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ LLM 调用失败 -> 返回空列表，不崩溃。"""
        repo.save_action(make_action())
        llm = FakeLLMClient(should_fail=True)
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec001")

        assert files == []


class TestPostGeneratorMultiSymbol:
    """多 symbol 分组测试。"""

    @pytest.mark.asyncio
    async def test_multiple_symbols_each_gets_post(self, repo, posts_dir: Path) -> None:
        """✅ 一次 execution 涉及多个 symbol -> 每个生成一篇。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        repo.save_action(make_action(symbol="ETHUSDT", reason_text="开仓 @ 3000"))
        llm = FakeLLMClient(response="贴文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec001")

        assert len(files) == 2
        symbols_in_files = {f.stem.split("_")[-1] for f in files}
        assert symbols_in_files == {"BTCUSDT", "ETHUSDT"}
        assert len(llm.prompts) == 2, "应为每个 symbol 调一次 LLM"


class TestPostGeneratorHistoricalPosts:
    """历史贴文去重测试。"""

    @pytest.mark.asyncio
    async def test_historical_posts_included_in_prompt(self, repo, posts_dir: Path) -> None:
        """✅ symbol 有历史贴文 -> 作为上下文传入 prompt。"""
        # 先生成一篇历史贴文
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm1 = FakeLLMClient(response="第一次开仓贴文")
        gen1 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm1)
        await gen1.generate_for_execution("exec001")

        # 再生成第二篇，prompt 应包含历史贴文
        repo.save_action(make_action(
            symbol="BTCUSDT", action_type="add",
            execution_id="exec002", reason_text="第 1 次加仓 @ 65500",
        ))
        llm2 = FakeLLMClient(response="加仓贴文")
        gen2 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm2)

        await gen2.generate_for_execution("exec002")

        assert len(llm2.prompts) == 1
        assert "第一次开仓贴文" in llm2.prompts[0], "历史贴文应出现在 prompt 中"

    @pytest.mark.asyncio
    async def test_no_historical_posts_shows_placeholder(self, repo, posts_dir: Path) -> None:
        """✅ 无历史贴文时 prompt 显示占位符。"""
        repo.save_action(make_action(symbol="SOLUSDT"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        assert "暂无历史贴文" in llm.prompts[0]

    @pytest.mark.asyncio
    async def test_historical_posts_include_timestamp(self, repo, posts_dir: Path) -> None:
        """✅ 历史贴文应带时间信息，帮助 LLM 理解发布时间。"""
        # 先生成一篇历史贴文（落库，含 created_at）
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm1 = FakeLLMClient(response="第一次开仓贴文XYZ")
        gen1 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm1)
        await gen1.generate_for_execution("exec001")

        # 再生成第二篇，prompt 应包含历史贴文的时间
        repo.save_action(make_action(
            symbol="BTCUSDT", action_type="add",
            execution_id="exec002", reason_text="第 1 次加仓 @ 65500",
        ))
        llm2 = FakeLLMClient(response="加仓贴文")
        gen2 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm2)

        await gen2.generate_for_execution("exec002")

        prompt = llm2.prompts[0]
        # 提取历史贴文渲染区：从"该币种历史贴文"到下一个"## "标题
        hist_start = prompt.find("该币种历史贴文")
        next_section = prompt.find("\n## ", hist_start + 1)
        hist_section = prompt[hist_start:next_section] if hist_start >= 0 else ""
        assert "第一次开仓贴文XYZ" in hist_section, "历史贴文正文应在历史贴文区域"
        assert "2026-" in hist_section, "历史贴文区域应带时间信息"

    @pytest.mark.asyncio
    async def test_load_historical_posts_returns_time_and_text(self, repo, posts_dir: Path) -> None:
        """✅ _load_historical_posts 返回带时间戳的贴文列表。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="测试贴文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)
        await gen.generate_for_execution("exec001")

        historical = gen._load_historical_posts("BTCUSDT")
        assert len(historical) == 1, "应返回 1 篇历史贴文"
        post = historical[0]
        assert "time" in post, "每篇历史贴文应含 time 字段"
        assert "text" in post, "每篇历史贴文应含 text 字段"
        assert post["text"] == "测试贴文"
        assert post["time"], "time 不应为空"


def make_content_action(
    symbol: str = "BTCUSDT",
    execution_id: str = "exec_content_001",
    strategy_name: str = "content_scan",
    reason_text: str = "BTCUSDT 连续 3 天上涨",
    signal_id: str = "sig001",
) -> StrategyActionRecord:
    """构造一个 content 类型的动作记录。"""
    return StrategyActionRecord(
        id=f"act_content_{symbol}",
        execution_id=execution_id,
        strategy_name=strategy_name,
        action_type="content",
        symbol=symbol,
        position_id="",
        order_id="",
        reason_text=reason_text,
        reason_data={
            "signal_type": "consecutive_rise",
            "direction": "bullish",
            "severity": 3,
            "metadata": {"streak_days": 3, "change_pct": 30.0},
        },
        signal_ids=[signal_id],
    )


class TestPostGeneratorContentPath:
    """内容型路径测试：content 动作 -> 走信号路径生成贴文。"""

    @pytest.mark.asyncio
    async def test_content_action_generates_post(self, repo, posts_dir: Path) -> None:
        """✅ content 动作 -> 生成贴文 -> 保存文件。"""
        repo.save_action(make_content_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 连涨3天，势头正猛！")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = await gen.generate_for_execution("exec_content_001")

        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "BTC 连涨3天，势头正猛！" in content

    @pytest.mark.asyncio
    async def test_content_prompt_uses_market_observer_role(self, repo, posts_dir: Path) -> None:
        """✅ content prompt 使用市场观察者角色（不是马丁做空）。"""
        repo.save_action(make_content_action(symbol="BTCUSDT"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec_content_001")

        assert len(llm.prompts) == 1
        assert "市场观察者" in llm.prompts[0], "应使用内容型角色"
        assert "马丁格尔做空" not in llm.prompts[0], "不应包含交易型角色"

    @pytest.mark.asyncio
    async def test_content_prompt_includes_signals(self, repo, posts_dir: Path) -> None:
        """✅ content prompt 应包含信号信息。"""
        # 先存信号
        from trading_service.repository.abc import SignalRecord
        repo.save_signal(SignalRecord(
            id="sig001",
            symbol="BTCUSDT",
            signal_type="consecutive_rise",
            direction="bullish",
            severity=3,
            description="BTCUSDT 连续 3 天上涨",
            metadata_json={"streak_days": 3, "change_pct": 30.0},
        ))
        repo.save_action(make_content_action(symbol="BTCUSDT", signal_id="sig001"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec_content_001")

        assert "consecutive_rise" in llm.prompts[0], "prompt 应包含信号类型"


class TestPostGeneratorPersistence:
    """贴文持久化测试：生成贴文后应落库到 trading_posts。"""

    @pytest.mark.asyncio
    async def test_trading_post_persisted_to_db(self, repo, posts_dir: Path) -> None:
        """✅ 交易型贴文生成后落库，含 prompt 和 post_text。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 做空入场！")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1, f"应落库 1 条贴文，实际 {len(posts)}"
        post = posts[0]
        assert post.execution_id == "exec001", f"execution_id 应为 exec001，实际 {post.execution_id}"
        assert post.symbol == "BTCUSDT", f"symbol 应为 BTCUSDT，实际 {post.symbol}"
        assert post.post_text == "BTC 做空入场！", "post_text 应为 LLM 返回的正文"
        assert post.prompt, "prompt 不应为空"
        assert "交易员" in post.prompt, f"trading prompt 应含交易员角色，实际: {post.prompt[:50]}"
        assert post.style == "trading", f"style 应为 trading，实际 {post.style}"
        assert post.action_type == "open", f"action_type 应为 open，实际 {post.action_type}"
        assert post.strategy_name == "martingale_short"

    @pytest.mark.asyncio
    async def test_content_post_persisted_to_db(self, repo, posts_dir: Path) -> None:
        """✅ 内容型贴文生成后落库，含 prompt 和 post_text。"""
        from trading_service.repository.abc import SignalRecord
        repo.save_signal(SignalRecord(
            id="sig001", symbol="BTCUSDT", signal_type="consecutive_rise",
            direction="bullish", severity=3, description="BTCUSDT 连续 3 天上涨",
            metadata_json={"streak_days": 3},
        ))
        repo.save_action(make_content_action(symbol="BTCUSDT", signal_id="sig001"))
        llm = FakeLLMClient(response="BTC 连涨3天！")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec_content_001")

        posts = repo.list_posts_by_execution("exec_content_001")
        assert len(posts) == 1, f"应落库 1 条贴文，实际 {len(posts)}"
        post = posts[0]
        assert post.post_text == "BTC 连涨3天！"
        assert post.prompt, "prompt 不应为空"
        assert "市场观察者" in post.prompt, f"content prompt 应含市场观察者角色"
        assert post.style == "content", f"style 应为 content，实际 {post.style}"
        assert post.action_type == "content", f"action_type 应为 content，实际 {post.action_type}"
        assert post.strategy_name == "content_scan"

    @pytest.mark.asyncio
    async def test_prompt_is_complete_llm_input(self, repo, posts_dir: Path) -> None:
        """✅ 落库的 prompt 应是发给 LLM 的完整提示词（与 FakeLLMClient 记录的一致）。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="贴文正文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1
        # FakeLLMClient 记录的 prompt 应与落库的 prompt 完全一致
        assert len(llm.prompts) == 1
        assert posts[0].prompt == llm.prompts[0], "落库的 prompt 应与发给 LLM 的 prompt 一致"

    @pytest.mark.asyncio
    async def test_multiple_symbols_each_persisted(self, repo, posts_dir: Path) -> None:
        """✅ 多 symbol 分组 -> 每个落库一条 PostRecord。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        repo.save_action(make_action(symbol="ETHUSDT", reason_text="开仓 @ 3000"))
        llm = FakeLLMClient(response="贴文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 2, f"应落库 2 条贴文，实际 {len(posts)}"
        symbols = {p.symbol for p in posts}
        assert symbols == {"BTCUSDT", "ETHUSDT"}

    @pytest.mark.asyncio
    async def test_llm_failure_no_post_persisted(self, repo, posts_dir: Path) -> None:
        """✅ LLM 调用失败 -> 不落库贴文。"""
        repo.save_action(make_action())
        llm = FakeLLMClient(should_fail=True)
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 0, "LLM 失败时不应落库贴文"

    @pytest.mark.asyncio
    async def test_no_llm_client_no_post_persisted(self, repo, posts_dir: Path) -> None:
        """✅ 无 LLM client -> 不落库贴文。"""
        repo.save_action(make_action())
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=None)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 0, "无 LLM client 时不应落库贴文"

    @pytest.mark.asyncio
    async def test_get_post_by_id(self, repo, posts_dir: Path) -> None:
        """✅ 落库后可通过 get_post(id) 查询单条。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="贴文正文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1
        fetched = repo.get_post(posts[0].id)
        assert fetched is not None, "get_post 应返回已落库的贴文"
        assert fetched.post_text == "贴文正文"
        assert fetched.prompt == posts[0].prompt
