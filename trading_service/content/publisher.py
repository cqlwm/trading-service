"""Binance Square 发帖发布器（异步管道）。

并发模型（关键）：
Playwright sync API 是**线程绑定**的--浏览器对象绑死在 `open()` 时的线程上，
之后所有操作必须在同一线程发起，否则抛 `Cannot switch to a different thread`。

本模块用一条**专属 worker 线程**串行消费发布队列，所有 Playwright 操作
（open / create_postx / close）都在该线程上执行，规避跨线程限制。

异步管道（关键）：
`enqueue` 入队后**立即返回**，不阻塞调用方（Playwright 截图+发帖耗时几十秒）。
worker 完成一个任务后，通过 `loop.call_soon_threadsafe` 把 async 回调
`on_success` / `on_failure` 调度回 asyncio 事件循环线程执行。
调用方（PostGenerator / API）不再阻塞等待，结果由回调异步回写。

浏览器释放时机（队列空触发）：
一批密集到达的任务复用同一浏览器实例；worker 处理完一个任务后用
`empty()` 检查队列，空则关闭 `BinanceService` 释放 Chrome 进程，
下一批任务到达时由 worker 重新打开。避免批量入队时反复开关浏览器。
（empty() 与下次 get() 间有极窄竞态窗口，可能偶发多余开关，稀疏任务下可忽略。）

设计要点：
- 配置外置：通过 binance-service 的 config.yaml 加载完整 AppConfig
- 懒启动：首次 enqueue 时才启动 worker 线程 + 浏览器
- 线程亲和：Playwright 操作固定在专属 worker 线程
- 队列空才释放浏览器：一批任务复用浏览器，队列排空才关 Chrome，避免反复开关
- 异步回调：成功/失败通过 async 回调在事件循环线程通知，不阻塞调用方
- 失败不重试：只调 on_failure，是否重试由调用方决定
"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from binance_service import AppConfig, BinanceService, load_config

from trading_service.utils.symbol import Symbol

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()

@runtime_checkable
class PublishCallbacks(Protocol):
    """发布结果回调（async，在事件循环线程上执行）。"""

    async def on_success(self, publish_id: str, share_link: str) -> None:
        """发布成功：携带 publish_id 与 share_link。"""
        ...

    async def on_failure(self, publish_id: str, error: str) -> None:
        """发布失败：携带 publish_id 与错误信息。不重试。"""
        ...


@runtime_checkable
class IPublisher(Protocol):
    """发布器接口，便于测试注入 Fake 实现。"""

    def enqueue(
        self, publish_id: str, base_asset: str, content: str,
        timeframe: str | None = None,
    ) -> None:
        """入队发布请求，立即返回（不阻塞）。结果通过回调通知。"""
        ...

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入事件循环（loop 线程调用，供 worker 调度 async 回调）。"""
        ...

    def close(self) -> None:
        """释放浏览器等资源。"""
        ...


@dataclass
class _PublishTask:
    """队列中的发布任务。"""
    publish_id: str
    base_asset: str
    content: str
    timeframe: str

def _timeout_exit(timeout: float, function) -> threading.Timer:
    timed_out = threading.Event()
    def _on_timeout() -> None:
        if timed_out.is_set():
            return
        timed_out.set()
        function()
        time.sleep(0.5)
        os._exit(1)
    timer = threading.Timer(timeout, _on_timeout)
    timer.daemon = True
    timer.start()
    return timer

class BinancePublisher:
    """Binance Square 异步发布器（封装 binance_service.BinanceService）。

    专属 worker 线程串行消费队列，Playwright 操作固定在该线程。
    enqueue 入队即返回；完成后通过 call_soon_threadsafe 调度 async 回调。
    一批任务复用浏览器，队列排空才关闭 Chrome 释放进程。

    watchdog（任务级超时）：
    单个发布任务有最大耗时上限 ``task_timeout_s``（默认 180s）。Playwright
    sync API 在 CDP 通道阻塞时会无限挂住（如 page.evaluate 不受 default
    timeout 约束），worker 线程会静默卡死。watchdog 用 threading.Timer 在
    超时后调 os._exit(1) 终止整个进程，由 systemd（Restart=always）10s 后
    自动拉起重启。比拿 Playwright 私有属性强杀 Chrome PID 更简单粗暴，但
    彻底干净——卡死状态、孤儿 Chrome、泄漏资源全清掉。dispatch on_failure
    在 os._exit 之前发出并短暂等待事件循环跑完（不保证 100% 投递，进程硬
    终止时回调可能丢）。重启后队列剩余任务会丢失（发帖业务可接受，人工
    补发）。systemd 配 StartLimitBurst 防系统性卡死进入循环重启。
    """

    # 默认任务超时：3 分钟。截图+发帖正常 30s 内完成，3 分钟足够宽容，
    # 超过则视为卡死，os._exit(1) 让 systemd 重启服务。
    _DEFAULT_TASK_TIMEOUT_S: float = 180.0

    # close 时等 worker 退出的 join 超时，超时后强杀 Chrome 解阻塞。
    _DEFAULT_CLOSE_JOIN_TIMEOUT_S: float = 10.0

    def __init__(
        self,
        config_path: str,
        timeframe: str = "1h",
        debug: bool = False,
        service_factory: Callable[[], BinanceService] | None = None,
        callbacks: PublishCallbacks | None = None,
        task_timeout_s: float = _DEFAULT_TASK_TIMEOUT_S,
        close_join_timeout_s: float = _DEFAULT_CLOSE_JOIN_TIMEOUT_S,
    ) -> None:
        self._config_path = config_path
        self._default_timeframe = timeframe
        self._debug = debug
        # _service 仅由 worker 线程读写
        self._service: BinanceService | None = None
        # service_factory 测试注入点：worker 内创建 service 时调用（含 open）
        self._service_factory = service_factory
        self._callbacks = callbacks
        self._loop: asyncio.AbstractEventLoop | None = None
        self._worker: threading.Thread | None = None
        self._task_queue: queue.Queue[object] = queue.Queue()
        self._task_timeout_s = task_timeout_s
        self._close_join_timeout_s = close_join_timeout_s

    def _load_config(self) -> AppConfig:
        """加载 binance-service 的 AppConfig（完整配置来自 YAML 文件）。"""
        return load_config(self._config_path)

    # ── 事件循环注入 ─────────────────────────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入事件循环（loop 线程调用一次，供 worker 调度 async 回调）。"""
        self._loop = loop

    # ── 对外接口：入队即返回 ─────────────────────────────────

    def enqueue(
        self, publish_id: str, base_asset: str, content: str,
        timeframe: str | None = None,
    ) -> None:
        """入队发布请求，立即返回（不阻塞）。结果通过回调通知。

        Args:
            publish_id: 发布任务标识（通常为 post_id），回调回传用于关联
            base_asset: 基础资产符号，如 "BTC"
            content: 帖子正文
            timeframe: K 线周期，None 时用构造时的默认值
        """
        tf = timeframe or self._default_timeframe
        task = _PublishTask(
            publish_id=publish_id, base_asset=base_asset,
            content=content, timeframe=tf,
        )
        self._task_queue.put(task)

        self._ensure_worker()
        if self._loop is None:
            logger.warning(
                "enqueue 时事件循环未注入，回调将无法调度（publish_id=%s）",
                publish_id,
            )

    # ── 专属 worker 线程 ─────────────────────────────────────

    def _ensure_worker(self) -> None:
        """懒启动 worker 线程（double-checked locking）。

        注：不重建 _task_queue。残留任务由 close() 在 worker 退出后排空，
        保证队列引用终身不变，避免"换队列"导致的新旧 worker 竞态。
        """
        if self._worker is not None and self._worker.is_alive():
            return
        with _LOCK:
            if self._worker is not None and self._worker.is_alive():
                return

            t = threading.Thread(
                target=self._worker_loop,
                name="BinancePublisherWorker",
                daemon=True,
            )
            t.start()

            self._worker = t
            logger.info("BinancePublisher worker 线程已启动")

    def _worker_loop(self) -> None:
        """worker 线程主循环：串行消费任务直至队列空 60s 超时退出。

        浏览器在**队列排空**时才释放（而非每个任务后）：一批密集到达的
        任务复用同一个浏览器实例，只在队列彻底空、无待发任务时关闭 Chrome。
        实现方式：处理完一个任务后用 empty() 检查队列；空则释放浏览器，
        再阻塞 get 等待新任务。

        已知权衡：empty() 与下一次 get() 之间存在极窄竞态窗口--若恰在
        empty() 返回 True 之后、get() 阻塞之前有新任务入队，浏览器会被
        释放后立即重开（多一次开关）。发布任务稀疏时影响可忽略，故接受。
        改用 get_nowait 原子取可消除该窗口，但当前简洁性优先。
        """
        while True:

            task_done = False
            try:
                task = self._task_queue.get(timeout=60)
                assert isinstance(task, _PublishTask)
                self._process_task(task)
                task_done = True
            except queue.Empty:
                self._release_service_on_worker()
                return
            finally:
                if task_done:
                    self._task_queue.task_done()


    def _process_task(self, task: _PublishTask) -> None:
        timer = _timeout_exit(self._task_timeout_s, lambda : logger.error(
            "发布任务超时（>%ss），重启服务: publish_id=%s",
            self._task_timeout_s, task.publish_id
        ))

        try:
            service = self._get_service_unsafe()
            link = service.create_postx(
                base_asset=task.base_asset,
                content=task.content,
                timeframe=task.timeframe,
                debug=self._debug,
            )
            if link is None:
                self._dispatch_failure(
                    task.publish_id,
                    f"postx 发布返回 None（可能发帖失败或被拦截）: {task.base_asset}",
                )
            else:
                self._dispatch_success(task.publish_id, link)
        except Exception as e:
            self._release_service_on_worker()
            self._dispatch_failure(task.publish_id, str(e))
        finally:
            timer.cancel()

    # ── 回调调度：worker 线程 -> 事件循环线程 ─────────────────

    def _dispatch_success(self, publish_id: str, share_link: str) -> None:
        """把 on_success 调度到事件循环线程。"""
        if self._callbacks is None or self._loop is None:
            logger.warning("发布成功但回调/loop 未配置，丢弃结果（publish_id=%s, link=%s）",publish_id, share_link)
            return

        if self._loop.is_closed():
            logger.warning("发布成功但事件循环已关闭，丢弃结果（publish_id=%s, link=%s）",publish_id, share_link)
            return

        coro = self._callbacks.on_success(publish_id, share_link)
        self._loop.call_soon_threadsafe(asyncio.create_task, coro)

    def _dispatch_failure(self, publish_id: str, error: str) -> None:
        """把 on_failure 调度到事件循环线程。"""
        if self._callbacks is None or self._loop is None:
            logger.warning("发布失败但回调/loop 未配置，丢弃结果（publish_id=%s, error=%s）",publish_id, error)
            return

        if self._loop.is_closed():
            logger.warning("发布失败但事件循环已关闭，丢弃结果（publish_id=%s, error=%s）",publish_id, error)
            return

        coro = self._callbacks.on_failure(publish_id, error)
        self._loop.call_soon_threadsafe(asyncio.create_task, coro)

    # ── service 生命周期（worker 线程内） ────────────────────

    def _get_service_unsafe(self) -> BinanceService:
        """在 worker 线程内获取/创建 service。"""
        if self._service is not None:
            return self._service
        if self._service_factory is not None:
            service = self._service_factory()
        else:
            service = BinanceService(app_config=self._load_config())
            service.open()
        self._service = service
        logger.info("BinancePublisher 浏览器已启动")
        return service

    def _release_service_on_worker(self) -> None:
        """在 worker 线程内关闭并丢弃当前 service（释放 Chrome 进程）。"""
        if self._service is None:
            return
        try:
            self._service.close()
        except Exception as e:
            logger.warning(f"发布后关闭 BinanceService 时异常: {e}")
        self._service = None
        logger.info("BinancePublisher 浏览器已释放（发布完成）")

    # ── 关闭 ─────────────────────────────────────────────────

    def close(self) -> None:
        self._drain_residual_tasks()
        self._release_service_on_worker()

    def _drain_residual_tasks(self) -> None:
        while True:
            try:
                self._task_queue.get_nowait()
            except queue.Empty:
                return
            self._task_queue.task_done()


def resolve_base_asset(symbol: str) -> str:
    """从交易对符号解析基础资产。

    "BTCUSDT" -> "BTC"，"BTC/USDT" -> "BTC"。
    解析失败时原样返回（容错）。
    """
    try:
        return Symbol.parse(symbol).base
    except ValueError:
        logger.warning(f"无法解析交易对 {symbol}，原样使用作为 base_asset")
        return symbol
