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

    def test_generates_post_and_saves_file(self, repo, posts_dir: Path) -> None:
        """✅ 有动作记录 -> 生成贴文 -> 保存文件。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 做空入场，目标明确！")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("exec001")

        assert len(files) == 1
        assert files[0].exists()
        content = files[0].read_text(encoding="utf-8")
        assert "BTC 做空入场，目标明确！" in content
        assert "BTCUSDT" in content

    def test_file_naming_format(self, repo, posts_dir: Path) -> None:
        """✅ 文件名格式: {timestamp}_{symbol}.md"""
        repo.save_action(make_action(symbol="ETHUSDT"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("exec001")

        assert len(files) == 1
        filename = files[0].name
        assert filename.endswith("_ETHUSDT.md"), f"文件名应以 _ETHUSDT.md 结尾，实际: {filename}"
        # 验证时间戳格式 YYYY-MM-DD_HHMMSS
        prefix = filename[:-len("_ETHUSDT.md")]
        datetime.strptime(prefix, "%Y-%m-%d_%H%M%S")

    def test_post_includes_action_metadata(self, repo, posts_dir: Path) -> None:
        """✅ 贴文文件底部应附本次执行动作记录。"""
        repo.save_action(make_action(
            symbol="BTCUSDT", action_type="add",
            reason_text="第 1 次加仓 @ 65500",
            reason_data={"action": "safety_order", "layer": 1},
        ))
        llm = FakeLLMClient(response="贴文正文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("exec001")

        content = files[0].read_text(encoding="utf-8")
        assert "第 1 次加仓 @ 65500" in content
        assert "safety_order" in content


class TestPostGeneratorSkipConditions:
    """跳过条件测试。"""

    def test_empty_actions_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ execution 无动作 -> 返回空列表，不调 LLM。"""
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("nonexistent_exec")

        assert files == []
        assert len(llm.prompts) == 0, "无动作时不应调用 LLM"

    def test_no_llm_client_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ client 为 None -> 返回空列表。"""
        repo.save_action(make_action())
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=None)

        files = gen.generate_for_execution("exec001")

        assert files == []

    def test_llm_failure_returns_empty(self, repo, posts_dir: Path) -> None:
        """✅ LLM 调用失败 -> 返回空列表，不崩溃。"""
        repo.save_action(make_action())
        llm = FakeLLMClient(should_fail=True)
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("exec001")

        assert files == []


class TestPostGeneratorMultiSymbol:
    """多 symbol 分组测试。"""

    def test_multiple_symbols_each_gets_post(self, repo, posts_dir: Path) -> None:
        """✅ 一次 execution 涉及多个 symbol -> 每个生成一篇。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        repo.save_action(make_action(symbol="ETHUSDT", reason_text="开仓 @ 3000"))
        llm = FakeLLMClient(response="贴文")
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        files = gen.generate_for_execution("exec001")

        assert len(files) == 2
        symbols_in_files = {f.stem.split("_")[-1] for f in files}
        assert symbols_in_files == {"BTCUSDT", "ETHUSDT"}
        assert len(llm.prompts) == 2, "应为每个 symbol 调一次 LLM"


class TestPostGeneratorHistoricalPosts:
    """历史贴文去重测试。"""

    def test_historical_posts_included_in_prompt(self, repo, posts_dir: Path) -> None:
        """✅ symbol 有历史贴文 -> 作为上下文传入 prompt。"""
        # 先生成一篇历史贴文
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm1 = FakeLLMClient(response="第一次开仓贴文")
        gen1 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm1)
        gen1.generate_for_execution("exec001")

        # 再生成第二篇，prompt 应包含历史贴文
        repo.save_action(make_action(
            symbol="BTCUSDT", action_type="add",
            execution_id="exec002", reason_text="第 1 次加仓 @ 65500",
        ))
        llm2 = FakeLLMClient(response="加仓贴文")
        gen2 = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm2)

        gen2.generate_for_execution("exec002")

        assert len(llm2.prompts) == 1
        assert "第一次开仓贴文" in llm2.prompts[0], "历史贴文应出现在 prompt 中"

    def test_no_historical_posts_shows_placeholder(self, repo, posts_dir: Path) -> None:
        """✅ 无历史贴文时 prompt 显示占位符。"""
        repo.save_action(make_action(symbol="SOLUSDT"))
        llm = FakeLLMClient()
        gen = PostGenerator(repo=repo, posts_dir=str(posts_dir), llm_client=llm)

        gen.generate_for_execution("exec001")

        assert "暂无历史贴文" in llm.prompts[0]
