"""测试 BinancePublisher 专属 worker 线程机制。

背景：Playwright sync API 是线程绑定的，浏览器对象绑死在 open() 时的线程上。
AsyncIOScheduler -> asyncio.to_thread -> 默认线程池的 worker 线程每次可能不同，
导致首次 open() 在 worker-1，后续 create_postx() 可能落在 worker-2，触发
"Cannot switch to a different thread"。

修复方案：BinancePublisher 内部起一条专属 worker 线程，open/create_postx/close
全部在该线程上执行，外部调用通过 queue + future 同步等待结果。

测试覆盖（TDD 红阶段）：
1. open 与 create_postx 在同一条线程（核心断言）
2. 多次 publish 始终用同一条 worker 线程
3. 从不同调用线程发起的 publish 仍落在同一条 worker 线程
4. close 后再次 publish 会重启 worker 线程
5. create_postx 抛异常时正常向调用方传播
6. 异常不污染 worker 线程（后续调用仍正常）
7. 并发 publish 串行执行（worker 单线程天然保证）
"""
from __future__ import annotations

import threading
import time

import pytest

from trading_service.content.publisher import BinancePublisher

# binance-service 真实配置文件，用于配置加载测试（路径与 config.local.yaml 一致）
BINANCE_CONFIG_PATH = "/Users/li/projects/binance-service/config.yaml"


class ThreadRecordingService:
    """记录所有调用所在线程 id 的内存版 BinanceService。

    用于验证 open() 与 create_postx() 是否在同一条线程上执行。
    """

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
        self.open_thread: int | None = None
        self.postx_threads: list[int] = []
        # 并发执行探测：记录是否有重叠调用
        self._active_count: int = 0
        self._max_concurrent: int = 0

    def open(self) -> None:
        with self._lock:
            self.open_thread = threading.get_ident()

    def close(self) -> None:
        # 记录 close 也发生在 worker 线程（与 open 一致）
        # 这里不强制断言，由测试侧读取
        pass

    def create_postx(
        self,
        base_asset: str,
        content: str,
        quote: str = "USDT",
        timeframe: str = "1h",
        debug: bool = False,
    ) -> str | None:
        with self._lock:
            self._active_count += 1
            self._max_concurrent = max(self._max_concurrent, self._active_count)
            current = threading.get_ident()
            self.postx_threads.append(current)
        try:
            if self._delay > 0:
                time.sleep(self._delay)
            if self._should_raise:
                raise RuntimeError("Playwright 操作失败")
            return self._share_link
        finally:
            with self._lock:
                self._active_count -= 1

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent


def _make_publisher(service: ThreadRecordingService) -> BinancePublisher:
    """构造注入了记录型 service 的 BinancePublisher（已就绪 service，不走 open）。"""
    publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH, timeframe="1h")
    publisher._service = service  # type: ignore[attr-defined]
    return publisher


def _make_publisher_with_factory(service: ThreadRecordingService) -> BinancePublisher:
    """构造注入 service 工厂的 BinancePublisher。

    worker 内创建 service 时调用工厂（含 open），用于验证
    open 与 create_postx 在同一条 worker 线程上的亲和性。
    """
    return BinancePublisher(
        config_path=BINANCE_CONFIG_PATH,
        timeframe="1h",
        service_factory=lambda: (service.open() or service),
    )


class TestWorkerThreadAffinity:
    """核心：open 与 create_postx 必须在同一条专属 worker 线程上。"""

    def test_open_and_publish_on_same_thread(self) -> None:
        """✅ 首次 publish 时 open() 与 create_postx() 在同一条线程。"""
        service = ThreadRecordingService()
        publisher = _make_publisher_with_factory(service)
        try:
            publisher.publish_postx(base_asset="BTC", content="test")
        finally:
            publisher.close()

        assert service.open_thread is not None, "open 应被调用并记录线程"
        assert len(service.postx_threads) == 1, "应有一次 create_postx"
        assert service.postx_threads[0] == service.open_thread, (
            f"open 线程 {service.open_thread} 与 publish 线程 "
            f"{service.postx_threads[0]} 不一致 -> 会触发 Playwright 跨线程错误"
        )

    def test_multiple_publishes_use_same_worker_thread(self) -> None:
        """✅ 多次 publish 始终落在同一条 worker 线程。"""
        service = ThreadRecordingService()
        publisher = _make_publisher_with_factory(service)
        try:
            publisher.publish_postx(base_asset="BTC", content="first")
            publisher.publish_postx(base_asset="ETH", content="second")
            publisher.publish_postx(base_asset="SOL", content="third")
        finally:
            publisher.close()

        assert len(service.postx_threads) == 3
        unique_threads = set(service.postx_threads)
        assert len(unique_threads) == 1, (
            f"所有 publish 应在同一 worker 线程，实际分布在 {unique_threads}"
        )

    def test_publish_from_different_caller_threads_hits_same_worker(self) -> None:
        """✅ 不同调用线程发起的 publish 都落到同一条 worker 线程。

        这是 asyncio.to_thread 默认线程池的真实场景模拟：调用方线程每次不同，
        但 Playwright 操作必须固定在一条 worker 上。
        """
        service = ThreadRecordingService()
        publisher = _make_publisher_with_factory(service)
        results: list[int] = []
        errors: list[BaseException] = []

        def publish_from_thread(content: str) -> None:
            try:
                publisher.publish_postx(base_asset="BTC", content=content)
                results.append(threading.get_ident())
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [
            threading.Thread(target=publish_from_thread, args=(f"t{i}",))
            for i in range(4)
        ]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            publisher.close()

        assert not errors, f"调用方不应有异常: {errors}"
        assert len(service.postx_threads) == 4
        # 调用方来自 4 条不同线程
        assert len(set(results)) == 4, "测试前提：调用方应在不同线程"
        # 但 Playwright 操作全在同一条 worker 线程
        assert len(set(service.postx_threads)) == 1, (
            f"worker 线程应唯一，实际: {set(service.postx_threads)}"
        )

    def test_publish_not_on_caller_thread(self) -> None:
        """✅ Playwright 操作不应在调用方线程上执行（否则就没了专属线程的意义）。"""
        service = ThreadRecordingService()
        publisher = _make_publisher_with_factory(service)
        caller_id = threading.get_ident()
        try:
            publisher.publish_postx(base_asset="BTC", content="test")
        finally:
            publisher.close()

        assert service.postx_threads[0] != caller_id, (
            "create_postx 不应在调用方线程执行，应在专属 worker 线程"
        )


class TestWorkerLifecycle:
    """worker 线程的生命周期：close 后重启、close 幂等。"""

    def test_close_then_publish_restarts_worker(self) -> None:
        """✅ close 让 worker 退出；再 publish 启动新 worker。

        真实语义：close 关闭 service 并让 worker 退出；再 publish 时 worker 重启。
        通过捕获两次的 worker 线程对象并断言 close 后旧 worker 已死亡来验证
        （线程 ID 在 daemon 退出后可能被 OS 复用，不能用 TID 判等）。
        """
        service1 = ThreadRecordingService()
        publisher = _make_publisher(service1)
        try:
            publisher.publish_postx(base_asset="BTC", content="first")
            first_worker = publisher._worker  # type: ignore[attr-defined]
            assert first_worker is not None

            publisher.close()
            assert publisher._service is None  # type: ignore[attr-defined]
            assert not first_worker.is_alive(), "close 后旧 worker 应已退出"

            # 模拟 worker 重启后重建 service：注入新实例
            service2 = ThreadRecordingService()
            publisher._service = service2  # type: ignore[attr-defined]
            publisher.publish_postx(base_asset="ETH", content="second")
            second_worker = publisher._worker  # type: ignore[attr-defined]
        finally:
            publisher.close()

        assert second_worker is not None, "再 publish 后应有新 worker"
        assert second_worker is not first_worker, "应启动新的 worker 线程对象"

    def test_close_idempotent(self) -> None:
        """✅ 多次 close 不崩溃。"""
        service = ThreadRecordingService()
        publisher = _make_publisher(service)
        publisher.close()
        publisher.close()
        publisher.close()


class TestErrorPropagation:
    """异常必须正常传播，且不污染 worker 线程。"""

    def test_exception_propagates_to_caller(self) -> None:
        """✅ create_postx 抛异常时向调用方传播。"""
        service = ThreadRecordingService(should_raise=True)
        publisher = _make_publisher(service)
        try:
            with pytest.raises(RuntimeError, match="Playwright 操作失败"):
                publisher.publish_postx(base_asset="BTC", content="test")
        finally:
            publisher.close()

    def test_exception_does_not_corrupt_worker(self) -> None:
        """✅ 一次异常后 worker 线程仍可正常服务后续调用。"""
        failing_service = ThreadRecordingService(should_raise=True)
        publisher = _make_publisher(failing_service)
        try:
            with pytest.raises(RuntimeError):
                publisher.publish_postx(base_asset="BTC", content="boom")

            # 切换为正常 service（模拟 service 重建场景）
            ok_service = ThreadRecordingService()
            publisher._service = ok_service  # type: ignore[attr-defined]
            link = publisher.publish_postx(base_asset="ETH", content="recovered")
        finally:
            publisher.close()

        assert link is not None, "异常后 worker 应能继续工作"


class TestConcurrency:
    """并发 publish 串行执行（worker 单线程天然保证）。"""

    def test_concurrent_publishes_are_serialized(self) -> None:
        """✅ 并发调用 publish_postx 时，create_postx 不重叠。"""
        service = ThreadRecordingService(delay=0.05)
        publisher = _make_publisher(service)
        errors: list[BaseException] = []

        def publish(content: str) -> None:
            try:
                publisher.publish_postx(base_asset="BTC", content=content)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [
            threading.Thread(target=publish, args=(f"c{i}",))
            for i in range(5)
        ]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        finally:
            publisher.close()

        assert not errors, f"并发调用不应有异常: {errors}"
        assert len(service.postx_threads) == 5, "5 次调用都应到达 service"
        assert service.max_concurrent == 1, (
            f"create_postx 应串行执行，max_concurrent={service.max_concurrent}"
        )
        # 且全部在同一条 worker 线程
        assert len(set(service.postx_threads)) == 1


class TestNoneReturn:
    """create_postx 返回 None 时仍按原契约抛 RuntimeError。"""

    def test_none_return_raises_runtime_error(self) -> None:
        """✅ create_postx 返回 None 时抛 RuntimeError（保持原行为）。"""
        service = ThreadRecordingService(share_link=None)
        publisher = _make_publisher(service)
        try:
            with pytest.raises(RuntimeError, match="postx 发布返回 None"):
                publisher.publish_postx(base_asset="BTC", content="test")
        finally:
            publisher.close()
