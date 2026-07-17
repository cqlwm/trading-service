"""Binance Square 发帖发布器。

封装 binance_service.BinanceService，提供线程安全的 postx 发布能力。
设计要点：
- 配置外置：通过 binance-service 的 config.yaml 加载完整 AppConfig（chrome/poster/screenshot 等）
- 懒加载：首次发布时才启动浏览器，避免启动即要求 storage_state 存在
- 线程安全：Playwright 同步 API 非线程安全，用 threading.Lock 串行化
- 单例复用：全局一个 BinanceService，多次发布共用浏览器，storage_state 自动续期
- 异步友好：publish_postx 是同步方法，由上层通过 asyncio.to_thread 调用
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

from binance_service import AppConfig, BinanceService, load_config

from trading_service.utils.symbol import Symbol

logger = logging.getLogger(__name__)


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

    浏览器懒加载单例：首次 publish_postx 时启动，close() 时关闭。
    threading.Lock 保证多线程调用串行化（Playwright 非线程安全）。
    """

    def __init__(
        self,
        config_path: str,
        timeframe: str = "1h",
        debug: bool = False,
    ) -> None:
        self._config_path = config_path
        self._default_timeframe = timeframe
        self._debug = debug
        self._service: BinanceService | None = None
        self._lock = threading.Lock()

    def _load_config(self) -> AppConfig:
        """加载 binance-service 的 AppConfig（完整配置来自 YAML 文件）。"""
        return load_config(self._config_path)

    def _get_service(self) -> BinanceService:
        """懒加载并返回 BinanceService 单例（double-checked locking）。"""
        if self._service is not None:
            return self._service
        with self._lock:
            if self._service is not None:
                return self._service
            service = BinanceService(app_config=self._load_config())
            service.open()
            self._service = service
            logger.info("BinancePublisher 浏览器已启动")
            return service

    def publish_postx(
        self, base_asset: str, content: str, timeframe: str | None = None
    ) -> str:
        """同步执行 postx（截图 + 发帖），返回 share_link。

        线程安全：通过 _lock 串行化浏览器操作。
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
        with self._lock:
            service = self._get_service_unsafe()
            link = service.create_postx(
                base_asset=base_asset,
                content=content,
                timeframe=tf,
                debug=self._debug,
            )
            if link is None:
                raise RuntimeError(
                    f"postx 发布返回 None（可能发帖失败或被拦截）: {base_asset}"
                )
            return link

    def _get_service_unsafe(self) -> BinanceService:
        """在已持锁的情况下获取/创建 service。"""
        if self._service is not None:
            return self._service
        service = BinanceService(app_config=self._load_config())
        service.open()
        self._service = service
        logger.info("BinancePublisher 浏览器已启动")
        return service

    def close(self) -> None:
        """关闭浏览器，释放资源。可重复调用。"""
        with self._lock:
            if self._service is not None:
                try:
                    self._service.close()
                except Exception as e:
                    logger.warning(f"关闭 BinanceService 时异常: {e}")
                self._service = None
                logger.info("BinancePublisher 浏览器已关闭")


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
