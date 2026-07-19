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
import queue
import threading
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


class BinancePublisher:
    """Binance Square 异步发布器（封装 binance_service.BinanceService）。

    专属 worker 线程串行消费队列，Playwright 操作固定在该线程。
    enqueue 入队即返回；完成后通过 call_soon_threadsafe 调度 async 回调。
    一批任务复用浏览器，队列排空才关闭 Chrome 释放进程。
    """

    # worker 队列哨兵：收到即退出循环
    _SHUTDOWN = object()

    def __init__(
        self,
        config_path: str,
        timeframe: str = "1h",
        debug: bool = False,
        service_factory: Callable[[], BinanceService] | None = None,
        callbacks: PublishCallbacks | None = None,
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
        """worker 线程主循环：串行消费任务直至收到哨兵。

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
            task = self._task_queue.get()
            try:
                if task is self._SHUTDOWN:
                    return

                assert isinstance(task, _PublishTask)
                self._process_task(task)

            finally:
                self._task_queue.task_done()

            if self._task_queue.empty():
                self._release_service_on_worker()


    def _process_task(self, task: _PublishTask) -> None:
        """在 worker 线程内执行单个发布任务：open+postx + 调度回调。

        浏览器由 _worker_loop 在队列排空时统一释放，本方法不关浏览器，
        以保证一批任务复用同一浏览器实例。
        开浏览器/发帖的任何异常都转 on_failure，不向外抛（避免杀死 worker）。
        """
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
        except BaseException as e:  # noqa: BLE001
            self._dispatch_failure(task.publish_id, str(e))
    # ── 回调调度：worker 线程 -> 事件循环线程 ─────────────────

    def _dispatch_success(self, publish_id: str, share_link: str) -> None:
        """把 on_success 调度到事件循环线程。"""
        if self._callbacks is None or self._loop is None:
            logger.warning(
                "发布成功但回调/loop 未配置，丢弃结果（publish_id=%s, link=%s）",
                publish_id, share_link,
            )
            return
        coro = self._callbacks.on_success(publish_id, share_link)
        self._loop.call_soon_threadsafe(asyncio.create_task, coro)

    def _dispatch_failure(self, publish_id: str, error: str) -> None:
        """把 on_failure 调度到事件循环线程。"""
        if self._callbacks is None or self._loop is None:
            logger.warning(
                "发布失败但回调/loop 未配置，丢弃结果（publish_id=%s, error=%s）",
                publish_id, error,
            )
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
        """让 worker 线程退出。可重复调用。

        worker 在跑时投哨兵、等其退出，再排空队列中残留的未消费任务
        （旧 worker 已死，单线程操作队列安全），并释放可能残留的浏览器。
        队列对象终身不变，避免 _ensure_worker 重建队列导致的新旧 worker 竞态。
        """
        with _LOCK:
            worker = self._worker
            if worker is None:
                return
            self._task_queue.put(self._SHUTDOWN)
            self._worker = None
        worker.join(timeout=10.0)
        if worker.is_alive():
            logger.warning("BinancePublisher worker 线程未在 10s 内退出")
        # 旧 worker 已退出，排空残留任务并释放浏览器
        self._drain_residual_tasks()
        self._release_service_on_worker()

    def _drain_residual_tasks(self) -> None:
        """排空队列中残留的未消费任务（close 后调用，单线程安全）。

        每个 get_nowait 都配一次 task_done，保持队列计数器平衡。
        """
        while True:
            try:
                task = self._task_queue.get_nowait()
            except queue.Empty:
                return
            try:
                if task is self._SHUTDOWN:
                    continue
                logger.warning(f"close 时丢弃未消费的发布任务: {task}")
            finally:
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
