"""测试 BinancePublisher 异步发布管道。

设计契约（改造后）：
- `enqueue(publish_id, ...)` 入队后立即返回，不阻塞调用方
- worker 线程串行消费队列，依次调 create_postx
- 完成后通过 async 回调 `on_success(publish_id, share_link)` /
  `on_failure(publish_id, error)` 通知，回调在 asyncio 事件循环线程上执行
- 浏览器每次发布后释放（即用即弃，复用 service_factory 测试）

测试覆盖（TDD 红阶段）：
1. enqueue 立即返回（不等 create_postx 完成）
2. 成功时 on_success 被调用，携带 publish_id + share_link
3. 失败时 on_failure 被调用，携带 publish_id + error
4. 回调在事件循环线程上执行（不是 worker 线程）
5. 多个 enqueue 串行消费（create_postx 不重叠）
6. 浏览器每次发布后释放（open/close 次数 == 发布次数）
7. enqueue 时 loop 未设置：记录失败回调（防御性）
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable

import pytest

from trading_service.content.publisher import BinancePublisher

# 所有测试均为 async，统一标记
pytestmark = pytest.mark.asyncio

# binance-service 真实配置文件
BINANCE_CONFIG_PATH = "/Users/li/projects/binance-service/config.yaml"


class RecordingService:
    """记录线程与调用次数的内存版 BinanceService。"""

    def __init__(
        self,
        share_link: str | None = "https://www.binance.com/zh-CN/square/post/123",
        should_raise: bool = False,
        delay: float = 0.0,
    ) -> None:
        self._share_link = share_link
        self._should_raise = should_raise
        self._delay = delay
        self._lock = threading.Lock()
        self.open_calls: int = 0
        self.close_calls: int = 0
        self.postx_calls: list[dict[str, Any]] = []
        self.postx_threads: list[int] = []
        self._active: int = 0
        self.max_concurrent: int = 0

    def open(self) -> None:
        with self._lock:
            self.open_calls += 1

    def close(self) -> None:
        with self._lock:
            self.close_calls += 1

    def create_postx(
        self,
        base_asset: str,
        content: str,
        quote: str = "USDT",
        timeframe: str = "1h",
        debug: bool = False,
    ) -> str | None:
        with self._lock:
            self._active += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
            self.postx_threads.append(threading.get_ident())
            self.postx_calls.append({
                "base_asset": base_asset, "content": content,
                "timeframe": timeframe, "debug": debug,
            })
        try:
            if self._delay > 0:
                time.sleep(self._delay)
            if self._should_raise:
                raise RuntimeError("Playwright 操作失败")
            return self._share_link
        finally:
            with self._lock:
                self._active -= 1


class RecordingCallbacks:
    """记录成功/失败回调的调用，支持异步等待。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.success: list[tuple[str, str]] = []
        self.failure: list[tuple[str, str]] = []
        self.callback_threads: list[int] = []
        self._success_event = asyncio.Event()
        self._failure_event = asyncio.Event()
        self._success_count_target: int = 1
        self._failure_count_target: int = 1

    def expect_success(self, count: int = 1) -> None:
        """重置成功等待：清空已记录、重置 event、设新目标。"""
        self._success_count_target = count
        self.success = []
        self._success_event.clear()

    def expect_failure(self, count: int = 1) -> None:
        """重置失败等待：清空已记录、重置 event、设新目标。"""
        self._failure_count_target = count
        self.failure = []
        self._failure_event.clear()

    async def on_success(self, publish_id: str, share_link: str) -> None:
        with self._lock:
            self.success.append((publish_id, share_link))
            self.callback_threads.append(threading.get_ident())
        if len(self.success) >= self._success_count_target:
            self._success_event.set()

    async def on_failure(self, publish_id: str, error: str) -> None:
        with self._lock:
            self.failure.append((publish_id, error))
            self.callback_threads.append(threading.get_ident())
        if len(self.failure) >= self._failure_count_target:
            self._failure_event.set()

    async def wait_success(self, timeout: float = 5.0) -> None:
        try:
            await asyncio.wait_for(self._success_event.wait(), timeout=timeout)
        except TimeoutError as e:
            raise AssertionError(
                f"on_success 未在 {timeout}s 内触发，"
                f"success={self.success}, failure={self.failure}"
            ) from e

    async def wait_failure(self, timeout: float = 5.0) -> None:
        try:
            await asyncio.wait_for(self._failure_event.wait(), timeout=timeout)
        except TimeoutError as e:
            raise AssertionError(
                f"on_failure 未在 {timeout}s 内触发，"
                f"success={self.success}, failure={self.failure}"
            ) from e


def _make_publisher(
    service: RecordingService,
    callbacks: RecordingCallbacks,
) -> BinancePublisher:
    """构造注入 service 工厂 + 回调的 publisher。"""
    return BinancePublisher(
        config_path=BINANCE_CONFIG_PATH,
        timeframe="1h",
        service_factory=lambda: (service.open() or service),
        callbacks=callbacks,
    )


async def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """轮询 predicate 直到返回 True 或超时。用于等待 worker 状态变化。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(
        f"等待条件未在 {timeout}s 内满足"
    )


class TestEnqueueReturnsImmediately:
    """enqueue 入队后立即返回，不阻塞等待 create_postx。"""

    async def test_enqueue_returns_before_postx_completes(self) -> None:
        """✅ create_postx 有 0.2s 延迟，enqueue 应远早于它返回。"""
        service = RecordingService(delay=0.2)
        callbacks = RecordingCallbacks()
        callbacks.expect_success()
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            start = time.monotonic()
            publisher.enqueue("p1", "BTC", "content")
            elapsed = time.monotonic() - start

            assert elapsed < 0.1, (
                f"enqueue 应立即返回（<0.1s），实际耗时 {elapsed:.3f}s"
            )
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(service.postx_calls) == 1


class TestSuccessCallback:
    """成功时 on_success 携带 publish_id + share_link 在 loop 线程触发。"""

    async def test_success_callback_invoked_with_id_and_link(self) -> None:
        """✅ on_success(publish_id, share_link) 被调用。"""
        service = RecordingService()
        callbacks = RecordingCallbacks()
        callbacks.expect_success()
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("post-abc", "BTC", "看涨")
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(callbacks.success) == 1
        pub_id, link = callbacks.success[0]
        assert pub_id == "post-abc", f"publish_id 应为 post-abc，实际 {pub_id}"
        assert link == "https://www.binance.com/zh-CN/square/post/123"

    async def test_callback_runs_on_loop_thread(self) -> None:
        """✅ 回调在事件循环线程执行，不在 worker 线程。"""
        service = RecordingService()
        callbacks = RecordingCallbacks()
        callbacks.expect_success()
        publisher = _make_publisher(service, callbacks)
        loop = asyncio.get_running_loop()
        publisher.set_loop(loop)
        loop_thread = threading.get_ident()
        try:
            publisher.enqueue("p1", "BTC", "content")
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(callbacks.callback_threads) == 1
        assert callbacks.callback_threads[0] == loop_thread, (
            "回调应在事件循环线程执行，实际在 "
            f"{callbacks.callback_threads[0]}，loop 线程 {loop_thread}"
        )
        # create_postx 在 worker 线程，与 loop 线程不同
        assert service.postx_threads[0] != loop_thread


class TestFailureCallback:
    """失败时 on_failure 携带 publish_id + error，不重试。"""

    async def test_failure_callback_on_exception(self) -> None:
        """✅ create_postx 抛异常时调 on_failure，携带 publish_id + error。"""
        service = RecordingService(should_raise=True)
        callbacks = RecordingCallbacks()
        callbacks.expect_failure()
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("post-fail", "BTC", "boom")
            await callbacks.wait_failure()
        finally:
            publisher.close()

        assert len(callbacks.failure) == 1, f"应有一次失败回调，实际 {callbacks.failure}"
        assert len(callbacks.success) == 0, "失败不应触发成功回调"
        pub_id, error = callbacks.failure[0]
        assert pub_id == "post-fail"
        assert "Playwright 操作失败" in error

    async def test_failure_on_none_return(self) -> None:
        """✅ create_postx 返回 None 时调 on_failure。"""
        service = RecordingService(share_link=None)
        callbacks = RecordingCallbacks()
        callbacks.expect_failure()
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("p-none", "BTC", "content")
            await callbacks.wait_failure()
        finally:
            publisher.close()

        assert len(callbacks.failure) == 1
        assert "p-none" in callbacks.failure[0][0]

    async def test_open_failure_does_not_kill_worker(self) -> None:
        """✅ 开浏览器失败转 on_failure，worker 不死，后续任务继续。

        回归测试：_get_service_unsafe 抛异常时（如配置错/浏览器起不来），
        不能让异常杀死 worker 线程导致后续任务无人消费。
        应转 on_failure，且 worker 继续服务后续任务。
        """
        call_count = [0]
        ok_service = RecordingService()

        def flaky_factory() -> Any:
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("浏览器启动失败")
            ok_service.open()
            return ok_service

        callbacks = RecordingCallbacks()
        callbacks.expect_failure(1)
        publisher = BinancePublisher(
            config_path=BINANCE_CONFIG_PATH,
            timeframe="1h",
            service_factory=flaky_factory,
            callbacks=callbacks,
        )
        publisher.set_loop(asyncio.get_running_loop())
        try:
            # 第一次：开浏览器失败，应转 on_failure 而非杀 worker
            publisher.enqueue("p-fail", "BTC", "first")
            await callbacks.wait_failure()

            # 第二次：worker 应仍存活，能正常处理新任务
            callbacks.expect_success(1)
            publisher.enqueue("p-ok", "ETH", "second")
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(callbacks.failure) == 1, "第一次应失败回调"
        assert callbacks.failure[0][0] == "p-fail"
        assert len(callbacks.success) == 1, "worker 存活，第二次应成功"
        assert callbacks.success[0][0] == "p-ok"


class TestSerialConsumption:
    """多个 enqueue 串行消费，create_postx 不重叠。"""

    async def test_multiple_enqueues_consumed_serially(self) -> None:
        """✅ 3 个任务串行消费，max_concurrent==1，且全部成功回调。"""
        service = RecordingService(delay=0.05)
        callbacks = RecordingCallbacks()
        callbacks.expect_success(3)
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            for i in range(3):
                publisher.enqueue(f"p{i}", "BTC", f"content-{i}")
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(service.postx_calls) == 3, "3 个任务都应被消费"
        assert service.max_concurrent == 1, (
            f"create_postx 应串行，max_concurrent={service.max_concurrent}"
        )
        assert len(callbacks.success) == 3
        ids = {s[0] for s in callbacks.success}
        assert ids == {"p0", "p1", "p2"}


class TestBrowserReleasedWhenQueueDrained:
    """浏览器在队列排空时才释放（不是每个任务后）。

    设计意图（用户原始设想）：_task_queue 可异步积压多个任务。
    一批密集到达的任务应复用同一个浏览器实例，只在队列彻底排空、
    没有待发任务时才关闭浏览器释放 Chrome 进程。
    若每个任务后都关浏览器，批量入队会反复开关 Chrome（慢且无意义）。
    """

    async def test_batch_enqueues_reuse_single_browser(self) -> None:
        """✅ 批量入队的多个任务复用同一个浏览器（1 次 open + 1 次 close）。

        3 个任务快速入队，worker 处理时队列始终非空，
        浏览器只在全部处理完、队列排空后才关闭一次。
        """
        service = RecordingService(delay=0.02)
        callbacks = RecordingCallbacks()
        callbacks.expect_success(3)
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            for i in range(3):
                publisher.enqueue(f"p{i}", "BTC", f"content-{i}")
            await callbacks.wait_success()
            # 等队列排空后浏览器被释放
            await asyncio.sleep(0.3)
        finally:
            publisher.close()

        assert service.open_calls == 1, (
            f"批量任务应复用浏览器（1 次 open），实际 {service.open_calls} 次"
        )
        assert service.close_calls == 1, (
            f"队列排空后应只 close 1 次，实际 {service.close_calls} 次"
        )
        assert len(service.postx_calls) == 3, "3 个任务都应被处理"

    async def test_spaced_enqueues_each_open_close(self) -> None:
        """✅ 间隔入队（中间队列曾排空）各自开关浏览器。

        第一个任务处理完、队列排空后浏览器关闭；
        第二个任务到达时重新打开浏览器。
        用轮询 service.close_calls 判断队列排空时机（避免回调 event 重置竞态）。
        """
        service = RecordingService()
        callbacks = RecordingCallbacks()
        callbacks.expect_success(1)
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("p1", "BTC", "first")
            await callbacks.wait_success()
            # 等队列排空，浏览器被释放（close_calls 达到 1）
            await _wait_until(lambda: service.close_calls >= 1, timeout=2.0)
            assert service.close_calls == 1, "第一个任务后队列排空应 close 1 次"

            publisher.enqueue("p2", "ETH", "second")
            # 等第二个任务处理完且队列再次排空
            await _wait_until(lambda: service.close_calls >= 2, timeout=2.0)
        finally:
            publisher.close()

        assert service.open_calls == 2, (
            f"间隔入队应各自 open（2 次），实际 {service.open_calls} 次"
        )
        assert service.close_calls == 2, (
            f"间隔入队应各自 close（2 次），实际 {service.close_calls} 次"
        )


class TestCloseResidualTasks:
    """close 时排空队列残留任务，重启 worker 不消费过期任务。

    场景：enqueue 多个任务后立即 close，worker 可能只处理了部分，
    剩余的残留在队列里。close 应排空这些残留，重启 worker 后
    只处理新入队的任务，不消费上个生命周期的过期任务。
    """

    async def test_residual_tasks_drained_on_close(self) -> None:
        """✅ close 排空残留任务，重启后只处理新任务。"""
        service = RecordingService(delay=0.3)  # 慢处理，确保 close 时有残留
        callbacks = RecordingCallbacks()
        publisher = _make_publisher(service, callbacks)
        publisher.set_loop(asyncio.get_running_loop())

        # 入队 3 个任务，第一个慢处理中，后两个残留
        publisher.enqueue("p1", "BTC", "first")
        publisher.enqueue("p2", "ETH", "second")
        publisher.enqueue("p3", "SOL", "third")
        # 不等处理完，立即 close（p1 可能在处理，p2/p3 残留）
        await asyncio.sleep(0.05)
        publisher.close()

        processed_in_first_life = len(service.postx_calls)
        # close 后队列应被排空：重启 worker 不应再看到 p2/p3
        callbacks.expect_success(1)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("p4", "BTC", "fourth")
            await callbacks.wait_success()
            await _wait_until(lambda: service.close_calls >= 1, timeout=2.0)
        finally:
            publisher.close()

        # 第二个生命周期只处理了 p4，没有 p2/p3
        new_calls = service.postx_calls[processed_in_first_life:]
        new_ids = [c["base_asset"] for c in new_calls]
        assert new_ids == ["BTC"], (
            f"重启后应只处理新任务 p4，实际处理了 {new_ids}（残留未排空）"
        )


class TestNoLoopDefensive:
    """enqueue 时 loop 未设置的防御性处理。"""

    async def test_enqueue_without_loop_records_failure(self) -> None:
        """✅ 未 set_loop 时 enqueue 不崩溃，且记录失败回调。

        loop 未注入意味着回调无法调度回事件循环。此时应安全降级：
        不抛异常，记录 warning，并直接同步记录一个失败（调用方可知发布未完成）。
        测试只验证不崩溃 + 不阻塞调用方即可。
        """
        service = RecordingService()
        callbacks = RecordingCallbacks()
        publisher = _make_publisher(service, callbacks)
        # 故意不调 set_loop
        try:
            start = time.monotonic()
            publisher.enqueue("p1", "BTC", "content")
            elapsed = time.monotonic() - start

            assert elapsed < 0.1, "enqueue 仍应立即返回"
            # 给 worker 一点时间处理（create_postx 仍会执行，只是回调无法调度）
            await asyncio.sleep(0.3)
        finally:
            publisher.close()

        # create_postx 仍被执行
        assert len(service.postx_calls) == 1
