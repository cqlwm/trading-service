"""Binance Square 发帖发布器。

封装 binance_service.BinanceService，提供线程安全的 postx 发布能力。

并发模型（关键）：
Playwright sync API 是**线程绑定**的——浏览器对象绑死在 `open()` 时的线程上，
之后所有操作必须在同一线程发起，否则抛
`Cannot switch to a different thread`。

调用链是 `AsyncIOScheduler -> asyncio.to_thread -> 默认线程池`，
默认线程池的 worker 每次可能不同，导致首次 `open()` 在 worker-1、
后续 `create_postx()` 落在 worker-2 触发跨线程错误。

解决：BinancePublisher 内部起**一条专属 worker 线程**，
`open / create_postx / close` 全部通过队列调度到该线程执行，
外部调用方（无论来自哪条线程）阻塞等待 future 结果。
worker 在首次 `publish` 时启动，`close` 时退出；再次 `publish` 重启。

设计要点：
- 配置外置：通过 binance-service 的 config.yaml 加载完整 AppConfig
- 懒加载：首次发布时才启动浏览器 + worker 线程
- 线程亲和：Playwright 操作固定在专属 worker 线程（本模块核心）
- 单例复用：worker 线程内全局一个 BinanceService，多次发布共用浏览器
- 异常透传：worker 内异常通过 future 回传给调用方，不污染 worker
- 异步友好：publish_postx 是同步方法，由上层通过 asyncio.to_thread 调用
"""
from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from typing import Callable, Protocol, TypeVar, runtime_checkable

from binance_service import AppConfig, BinanceService, load_config

from trading_service.utils.symbol import Symbol

logger = logging.getLogger(__name__)

T = TypeVar("T")

# worker 队列任务：要么是哨兵 _SHUTDOWN，要么是 (callable, future) 元组
_ShutdownToken = object
_WorkTask = tuple[Callable[[], object], "Future[object]"]
_WorkItem = _ShutdownToken | _WorkTask


@runtime_checkable
class IPublisher(Protocol):
    """发布器接口，便于测试注入 Fake 实现。"""

    def publish_postx(
        self, base_asset: str, content: str, timeframe: str | None = None
    ) -> str:
        """发布 postx（截图 + 发帖），成功返回 share_link，失败抛异常。"""
        ...

    def close(self) -> None:
        """释放浏览器等资源。"""
        ...


class BinancePublisher:
    """Binance Square 发布器（封装 binance_service.BinanceService）。

    浏览器懒加载单例 + 专属 worker 线程：首次 publish_postx 时启动 worker
    并在 worker 内启动浏览器，close() 时关闭浏览器并让 worker 退出。
    所有 Playwright 操作都串行地在同一条 worker 线程上执行，
    规避 Playwright sync API 的跨线程限制。
    """

    # worker 线程收到的哨兵任务：收到即退出循环
    _SHUTDOWN: _ShutdownToken = object()

    def __init__(
        self,
        config_path: str,
        timeframe: str = "1h",
        debug: bool = False,
        service_factory: Callable[[], BinanceService] | None = None,
    ) -> None:
        self._config_path = config_path
        self._default_timeframe = timeframe
        self._debug = debug
        # _service 仅由 worker 线程读写，外部测试可注入以绕过真实浏览器
        self._service: BinanceService | None = None
        # service_factory 测试注入点：worker 内创建 service 时调用（含 open）。
        # 默认 None 时走真实路径（load_config + BinanceService + open）。
        self._service_factory = service_factory
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._task_queue: queue.Queue[_WorkItem] = queue.Queue()

    def _load_config(self) -> AppConfig:
        """加载 binance-service 的 AppConfig（完整配置来自 YAML 文件）。"""
        return load_config(self._config_path)

    # ── 专属 worker 线程 ─────────────────────────────────────

    def _ensure_worker(self) -> None:
        """懒启动 worker 线程（double-checked locking）。"""
        if self._worker is not None and self._worker.is_alive():
            return
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            # 旧线程已退出，重建队列避免残留任务
            self._task_queue = queue.Queue()
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="BinancePublisherWorker",
                daemon=True,
            )
            self._worker.start()
            logger.info("BinancePublisher worker 线程已启动")

    def _worker_loop(self) -> None:
        """worker 线程主循环：消费任务直至收到哨兵。"""
        while True:
            task = self._task_queue.get()
            try:
                if task is self._SHUTDOWN:
                    return
                # 非哨兵任务：解构 (callable, future) 在本线程执行
                assert isinstance(task, tuple)
                func, fut = task
                if fut.set_running_or_notify_cancel():
                    try:
                        result = func()
                        fut.set_result(result)
                    except BaseException as e:  # noqa: BLE001
                        fut.set_exception(e)
            except BaseException:  # noqa: BLE001 - 防御性，不应发生
                logger.exception("BinancePublisher worker 循环异常")
            finally:
                if task is not self._SHUTDOWN:
                    self._task_queue.task_done()

    def _submit(self, func: Callable[[], T]) -> T:
        """把 callable 投到 worker 线程执行，阻塞等待结果（异常透传）。"""
        self._ensure_worker()
        fut: Future[T] = Future()
        assert self._task_queue is not None
        self._task_queue.put((func, fut))
        return fut.result()

    # ── 对外接口 ─────────────────────────────────────────────

    def publish_postx(
        self, base_asset: str, content: str, timeframe: str | None = None
    ) -> str:
        """同步执行 postx（截图 + 发帖），返回 share_link。

        所有 Playwright 操作调度到专属 worker 线程执行，调用方阻塞等待。
        失败时抛出异常，由调用方捕获并记录。

        Args:
            base_asset: 基础资产符号，如 "BTC"（不含 quote）
            content: 帖子正文
            timeframe: K 线周期，None 时用构造时的默认值

        Returns:
            Binance Square 的分享链接 share_link

        Raises:
            Exception: 截图或发帖过程中的任何错误
        """
        tf = timeframe or self._default_timeframe
        return self._submit(
            lambda: self._publish_on_worker(
                base_asset=base_asset, content=content, timeframe=tf
            )
        )

    def _publish_on_worker(
        self, base_asset: str, content: str, timeframe: str
    ) -> str:
        """在 worker 线程内执行：获取/创建 service + 调 create_postx。"""
        service = self._get_service_unsafe()
        link = service.create_postx(
            base_asset=base_asset,
            content=content,
            timeframe=timeframe,
            debug=self._debug,
        )
        if link is None:
            raise RuntimeError(
                f"postx 发布返回 None（可能发帖失败或被拦截）: {base_asset}"
            )
        return link

    def _get_service_unsafe(self) -> BinanceService:
        """在 worker 线程内获取/创建 service 单例。"""
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

    def close(self) -> None:
        """关闭浏览器并让 worker 线程退出。可重复调用。

        两种情形：
        - worker 在跑：在 worker 线程内关 service（保证线程亲和），再让 worker 退出。
        - worker 没跑但 _service 已注入（测试直接注入场景）：
          在当前线程关 service。无 Playwright greenlet 需要保护。
        """
        with self._lock:
            worker = self._worker
            service = self._service
            if worker is None:
                # worker 未启动：直接在当前线程关已注入的 service
                self._close_service_in_place(service)
                return
            # worker 在跑：调度到 worker 线程关闭，保证 Playwright 线程亲和
            self._submit(self._close_service_on_worker)
            self._task_queue.put(self._SHUTDOWN)
            self._worker = None
        # 锁外 join，避免与 _ensure_worker 抢锁死锁
        worker.join(timeout=10.0)
        if worker.is_alive():
            logger.warning("BinancePublisher worker 线程未在 10s 内退出")

    def _close_service_in_place(self, service: BinanceService | None) -> None:
        """在当前线程关闭已注入但 worker 未启动的 service（测试场景）。"""
        if service is None:
            return
        try:
            service.close()
        except Exception as e:
            logger.warning(f"关闭 BinanceService 时异常: {e}")
        self._service = None
        logger.info("BinancePublisher 浏览器已关闭")

    def _close_service_on_worker(self) -> None:
        """在 worker 线程内关闭浏览器。"""
        self._close_service_in_place(self._service)


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
