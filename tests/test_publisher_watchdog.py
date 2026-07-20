"""测试 BinancePublisher 的 watchdog 机制（任务超时重启服务）。

背景：worker 线程串行消费发布任务，单次 Playwright 调用若卡死
（如 CDP 通道阻塞时 page.evaluate 无限挂），整个 worker 会静默卡死，
无任何机制检测，只能靠用户 Ctrl+C。

watchdog 设计契约（超时重启服务）：
- 每个任务有最大耗时上限（默认 180s，构造参数 task_timeout_s 可注入便于测试）
- 任务超时后从 Timer 线程调 os._exit(1) 终止进程，由 systemd
  （Restart=always + RestartSec=10）自动拉起重启
- dispatch on_failure 在 os._exit 之前发出并短暂等待事件循环跑完
  （不保证 100% 投递，进程硬终止时回调可能丢）
- 重启后队列剩余任务会丢失（发帖业务可接受，人工补发）
- systemd 配 StartLimitIntervalSec/Burst 防系统性卡死进入循环重启

为何不用 force_kill Chrome PID 路径：
- Playwright 内部属性拿 Chrome PID 风险高（私有 API，版本升级可能坏）
- Chrome 残留孤儿进程风险
- 重启方案彻底干净，卡死状态/孤儿/泄漏全清掉

测试覆盖：
1. 正常完成不触发 watchdog（os._exit 不被调）
2. create_postx 卡住超时：os._exit 被调 + on_failure 被 dispatch
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


class KillableService:
    """可模拟「create_postx 卡住」的内存版 service。

    新契约下 watchdog 超时调 os._exit(1) 杀进程，create_postx 不需要被
    "解阻塞"——它随进程一起死。测试用 monkeypatch mock os._exit 让进程
    不真死，create_postx 继续阻塞。测试结束后调 unblock() 让 worker 能退出。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.open_calls: int = 0
        self.close_calls: int = 0
        self.postx_calls: list[dict[str, Any]] = []
        self._unblock_event = threading.Event()
        self._blocked = False

    def open(self) -> None:
        with self._lock:
            self.open_calls += 1

    def close(self) -> None:
        with self._lock:
            self.close_calls += 1

    def unblock(self) -> None:
        """测试结束后调，让卡住的 create_postx 返回（让 worker 能退出）。"""
        self._unblock_event.set()

    def create_postx(
        self,
        base_asset: str,
        content: str,
        quote: str = "USDT",
        timeframe: str = "1h",
        debug: bool = False,
    ) -> str | None:
        with self._lock:
            self.postx_calls.append({
                "base_asset": base_asset, "content": content,
                "timeframe": timeframe, "debug": debug,
            })
            self._blocked = True

        # 阻塞直到测试调 unblock（模拟 worker 卡死，等 os._exit 或测试结束）
        self._unblock_event.wait(timeout=5.0)
        with self._lock:
            self._blocked = False
        # mock os._exit 后进程没死，create_postx 返回前抛异常让 worker 走 except 分支
        raise RuntimeError("TargetClosedError: 模拟进程被杀后调用抛异常")

    @property
    def is_blocked(self) -> bool:
        with self._lock:
            return self._blocked


class RecordingCallbacks:
    """记录成功/失败回调的调用，支持异步等待。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.success: list[tuple[str, str]] = []
        self.failure: list[tuple[str, str]] = []
        self._success_event = asyncio.Event()
        self._failure_event = asyncio.Event()
        self._success_count_target: int = 1
        self._failure_count_target: int = 1

    def expect_success(self, count: int = 1) -> None:
        self._success_count_target = count
        self.success = []
        self._success_event.clear()

    def expect_failure(self, count: int = 1) -> None:
        self._failure_count_target = count
        self.failure = []
        self._failure_event.clear()

    async def on_success(self, publish_id: str, share_link: str) -> None:
        with self._lock:
            self.success.append((publish_id, share_link))
        if len(self.success) >= self._success_count_target:
            self._success_event.set()

    async def on_failure(self, publish_id: str, error: str) -> None:
        with self._lock:
            self.failure.append((publish_id, error))
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
    service: Any,
    callbacks: RecordingCallbacks,
    task_timeout_s: float = 0.3,
) -> BinancePublisher:
    """构造注入 service 工厂 + 回调 + 短 watchdog timeout 的 publisher。"""
    return BinancePublisher(
        config_path=BINANCE_CONFIG_PATH,
        timeframe="1h",
        service_factory=lambda: (service.open() or service),
        callbacks=callbacks,
        task_timeout_s=task_timeout_s,
    )


async def _wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"等待条件未在 {timeout}s 内满足")


class TestWatchdogDoesNotFireOnSuccess:
    """正常完成不触发 watchdog（os._exit 不被调）。"""

    async def test_fast_success_no_exit(self) -> None:
        """✅ create_postx 快速返回成功，watchdog 不触发 os._exit。"""
        from tests.test_publisher_async import RecordingService
        service = RecordingService()  # 立即返回成功
        callbacks = RecordingCallbacks()
        callbacks.expect_success()
        publisher = BinancePublisher(
            config_path=BINANCE_CONFIG_PATH,
            timeframe="1h",
            service_factory=lambda: (service.open() or service),
            callbacks=callbacks,
            task_timeout_s=0.3,
        )
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("p1", "BTC", "content")
            await callbacks.wait_success()
        finally:
            publisher.close()

        assert len(callbacks.success) == 1
        # 正常完成路径，watchdog 不触发 os._exit；用 close_calls 验证走正常 close
        assert service.close_calls >= 1


class TestWatchdogExitOnTimeout:
    """create_postx 卡住超时：os._exit 被调 + on_failure 被 dispatch。"""

    async def test_timeout_triggers_os_exit_and_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """✅ create_postx 阻塞超过 watchdog 阈值 -> os._exit(1) + on_failure。"""
        exit_called = threading.Event()

        def fake_exit(code: int) -> None:
            # mock：不真死进程，set event 让测试能断言 + 继续
            exit_called.set()

        monkeypatch.setattr(
            "trading_service.content.publisher.os._exit", fake_exit
        )

        service = KillableService()
        callbacks = RecordingCallbacks()
        callbacks.expect_failure()
        publisher = _make_publisher(service, callbacks, task_timeout_s=0.3)
        publisher.set_loop(asyncio.get_running_loop())
        try:
            publisher.enqueue("p-timeout", "BTC", "stuck")
            await callbacks.wait_failure(timeout=3.0)
            # 等 _on_timeout 跑完（dispatch + sleep 0.5 + os._exit mock）
            await _wait_until(lambda: exit_called.is_set(), timeout=3.0)
        finally:
            service.unblock()  # 让卡住的 worker 能退出
            publisher.close()

        assert exit_called.is_set(), "watchdog 超时应调 os._exit(1)"
        assert len(callbacks.failure) == 1, (
            f"应有一次失败回调，实际 {callbacks.failure}"
        )
        pub_id, error = callbacks.failure[0]
        assert pub_id == "p-timeout"
        assert "超时" in error or "timeout" in error.lower(), (
            f"失败信息应说明超时，实际: {error}"
        )
