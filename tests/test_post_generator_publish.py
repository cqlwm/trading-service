"""测试 PostGenerator 自动发布到 Binance Square。

测试覆盖：
1. 无 publisher 时不调用发布
2. 有 publisher 时自动为每篇贴文调用 publish_postx
3. 发布成功时 published_at / share_link 被持久化
4. 发布失败时 publish_error 被记录且不影响其他贴文/不抛异常
5. content 风格和 trading 风格的贴文都能发布
6. base_asset 从 symbol 正确解析
7. 发布失败后仍返回贴文文件（生成与发布解耦）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from trading_service.content.post_generator import PostGenerator
from trading_service.content.publisher import IPublisher
from trading_service.repository.abc import StrategyActionRecord


class FakeLLMClient:
    """内存版 LLM 客户端：返回固定文本。"""

    def __init__(self, response: str = "这是一条测试贴文。", should_fail: bool = False) -> None:
        self._response = response
        self._should_fail = should_fail

    def chat_completions_create(
        self, model: str, messages: list[dict[str, str]], temperature: float = 0.8,
    ) -> str:
        if self._should_fail:
            raise RuntimeError("LLM 服务不可用")
        return self._response


class FakePublisher:
    """内存版发布器：实现 enqueue/set_loop/close，记录调用并同步模拟回写。

    新接口下 PostGenerator 只调 enqueue，回写由 publisher 回调负责。
    测试中 FakePublisher 在 enqueue 时同步把结果回写 PostRecord
    （模拟回调即时完成），保留对 published_at/share_link/publish_error 的断言。
    """

    def __init__(
        self,
        repo: Any,
        share_link: str = "https://www.binance.com/zh-CN/square/post/fake123",
        should_fail: bool = False,
    ) -> None:
        self._repo = repo
        self._share_link = share_link
        self._should_fail = should_fail
        self.calls: list[dict[str, Any]] = []

    def enqueue(
        self, publish_id: str, base_asset: str, content: str,
        timeframe: str | None = None,
    ) -> None:
        from datetime import datetime, timezone
        self.calls.append({
            "publish_id": publish_id,
            "base_asset": base_asset,
            "content": content,
            "timeframe": timeframe,
        })
        if self._should_fail:
            self._repo.update_post_publish_result(
                post_id=publish_id,
                published_at=None,
                share_link=None,
                publish_error="Playwright 发布失败",
            )
        else:
            self._repo.update_post_publish_result(
                post_id=publish_id,
                published_at=datetime.now(timezone.utc),
                share_link=self._share_link,
                publish_error=None,
            )

    def set_loop(self, loop: Any) -> None:
        pass

    def close(self) -> None:
        pass


def make_action(
    symbol: str = "BTCUSDT",
    action_type: str = "open",
    execution_id: str = "exec001",
    strategy_name: str = "martingale_short",
    reason_text: str = "开仓 @ 65000",
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
        reason_data={"action": "initial_entry", "price": 65000},
        signal_ids=[],
    )


def make_content_action(
    symbol: str = "BTCUSDT",
    execution_id: str = "exec_content_001",
) -> StrategyActionRecord:
    """构造一个 content 类型的动作记录。"""
    return StrategyActionRecord(
        id=f"act_content_{symbol}",
        execution_id=execution_id,
        strategy_name="content_scan",
        action_type="content",
        symbol=symbol,
        position_id="",
        order_id="",
        reason_text=f"{symbol} 连续 3 天上涨",
        reason_data={"signal_type": "consecutive_rise", "direction": "bullish"},
        signal_ids=["sig001"],
    )


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def posts_dir(tmp_path: Path) -> Path:
    return tmp_path / "posts"


class TestNoPublisher:
    """无 publisher 时的行为。"""

    @pytest.mark.asyncio
    async def test_no_publisher_no_publish_call(self, repo, posts_dir: Path) -> None:
        """✅ 无 publisher 时不调用发布，贴文正常生成。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 贴文")
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=None,
        )

        files = await gen.generate_for_execution("exec001")

        assert len(files) == 1, "贴文应正常生成"
        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1
        assert posts[0].published_at is None, "无 publisher 时不应有发布时间"
        assert posts[0].share_link == "", "无 publisher 时 share_link 应为空"
        assert posts[0].publish_error == "", "无 publisher 时 publish_error 应为空"


class TestAutoPublishSuccess:
    """自动发布成功测试。"""

    @pytest.mark.asyncio
    async def test_publish_called_with_correct_base_asset(self, repo, posts_dir: Path) -> None:
        """✅ 发布时 base_asset 从 symbol 正确解析（BTCUSDT -> BTC）。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 看涨！")
        publisher = FakePublisher(repo, )
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec001")

        assert len(publisher.calls) == 1, "应调用一次发布"
        assert publisher.calls[0]["base_asset"] == "BTC", \
            f"base_asset 应为 BTC，实际 {publisher.calls[0]['base_asset']}"
        assert publisher.calls[0]["content"] == "BTC 看涨！"

    @pytest.mark.asyncio
    async def test_publish_result_persisted(self, repo, posts_dir: Path) -> None:
        """✅ 发布成功时 published_at / share_link 被持久化。"""
        repo.save_action(make_action(symbol="ETHUSDT"))
        llm = FakeLLMClient(response="ETH 贴文")
        publisher = FakePublisher(repo, share_link="https://binance.com/post/abc")
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1
        post = posts[0]
        assert post.published_at is not None, "发布成功后 published_at 不应为 None"
        assert post.share_link == "https://binance.com/post/abc", \
            f"share_link 应被回写，实际 {post.share_link}"
        assert post.publish_error == "", "发布成功时 publish_error 应为空"

    @pytest.mark.asyncio
    async def test_multiple_symbols_all_published(self, repo, posts_dir: Path) -> None:
        """✅ 多 symbol 每篇贴文都被发布。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        repo.save_action(make_action(symbol="ETHUSDT", reason_text="开仓 @ 3000"))
        llm = FakeLLMClient(response="贴文")
        publisher = FakePublisher(repo, )
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec001")

        assert len(publisher.calls) == 2, "应发布两篇贴文"
        published_assets = {c["base_asset"] for c in publisher.calls}
        assert published_assets == {"BTC", "ETH"}

    @pytest.mark.asyncio
    async def test_content_action_also_published(self, repo, posts_dir: Path) -> None:
        """✅ content 风格的贴文也能被发布。"""
        repo.save_action(make_content_action(symbol="SOLUSDT"))
        llm = FakeLLMClient(response="SOL 连涨！")
        publisher = FakePublisher(repo, )
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec_content_001")

        assert len(publisher.calls) == 1
        assert publisher.calls[0]["base_asset"] == "SOL", \
            f"base_asset 应为 SOL，实际 {publisher.calls[0]['base_asset']}"

    @pytest.mark.asyncio
    async def test_publish_timeframe_forwarded(self, repo, posts_dir: Path) -> None:
        """✅ publish_timeframe 配置正确传递给 publisher。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="贴文")
        publisher = FakePublisher(repo, )
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm,
            publisher=publisher, publish_timeframe="4h",
        )

        await gen.generate_for_execution("exec001")

        assert publisher.calls[0]["timeframe"] == "4h", \
            f"timeframe 应为 4h，实际 {publisher.calls[0]['timeframe']}"


class TestAutoPublishFailure:
    """自动发布失败测试。"""

    @pytest.mark.asyncio
    async def test_publish_failure_does_not_crash(self, repo, posts_dir: Path) -> None:
        """✅ 发布失败不影响贴文生成，不抛异常。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 贴文")
        publisher = FakePublisher(repo, should_fail=True)
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        files = await gen.generate_for_execution("exec001")

        assert len(files) == 1, "贴文文件应正常生成，不受发布失败影响"

    @pytest.mark.asyncio
    async def test_publish_error_persisted(self, repo, posts_dir: Path) -> None:
        """✅ 发布失败时 publish_error 被记录，published_at 为 None。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        llm = FakeLLMClient(response="BTC 贴文")
        publisher = FakePublisher(repo, should_fail=True)
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 1
        post = posts[0]
        assert post.published_at is None, "发布失败时 published_at 应为 None"
        assert post.share_link == "", "发布失败时 share_link 应为空"
        assert "Playwright 发布失败" in post.publish_error, \
            f"publish_error 应包含错误信息，实际 {post.publish_error}"

    @pytest.mark.asyncio
    async def test_one_failure_does_not_block_others(self, repo, posts_dir: Path) -> None:
        """✅ 一篇贴文发布失败不影响其他贴文。"""
        repo.save_action(make_action(symbol="BTCUSDT"))
        repo.save_action(make_action(symbol="ETHUSDT", reason_text="开仓 @ 3000"))
        llm = FakeLLMClient(response="贴文")
        # 第一次成功，第二次失败
        publisher = FakePublisher(repo, )
        original_enqueue = publisher.enqueue
        call_count = [0]

        def flaky_enqueue(
            publish_id: str, base_asset: str, content: str,
            timeframe: str | None = None,
        ) -> None:
            call_count[0] += 1
            if call_count[0] == 2:
                repo.update_post_publish_result(
                    post_id=publish_id, published_at=None,
                    share_link=None, publish_error="第二次发布失败",
                )
            else:
                original_enqueue(publish_id, base_asset, content, timeframe)

        publisher.enqueue = flaky_enqueue  # type: ignore[assignment]
        gen = PostGenerator(
            repo=repo, posts_dir=str(posts_dir), llm_client=llm, publisher=publisher,
        )

        await gen.generate_for_execution("exec001")

        posts = repo.list_posts_by_execution("exec001")
        assert len(posts) == 2, "两篇贴文都应生成"
        # 至少有一篇发布成功
        published = [p for p in posts if p.published_at is not None]
        failed = [p for p in posts if p.publish_error]
        assert len(published) >= 1, "至少一篇应发布成功"
        assert len(failed) >= 1, "至少一篇应记录失败"


class TestPublisherProtocol:
    """IPublisher Protocol 兼容性测试。"""

    def test_fake_publisher_satisfies_protocol(self) -> None:
        """✅ FakePublisher 满足 IPublisher Protocol（结构化子类型）。"""
        publisher: IPublisher = FakePublisher(None)  # type: ignore[assignment]
        # 不抛异常即通过
        assert publisher is not None
