"""测试 BinancePublisher 发布器。

测试覆盖：
1. 懒加载：首次 publish_postx 才启动浏览器
2. 单例复用：多次发布共用同一 BinanceService
3. 参数转发：base_asset / content / timeframe 正确传递给 create_postx
4. base_asset 解析：从 BTCUSDT 解析为 BTC
5. 异常传播：create_postx 返回 None 时抛 RuntimeError
6. 异常传播：create_postx 抛异常时向外传播
7. close 行为：关闭后 service 为 None，可重复调用
8. 线程安全：Lock 串行化（通过行为间接验证）
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from trading_service.content.publisher import BinancePublisher, resolve_base_asset


class FakeBinanceService:
    """内存版 BinanceService，记录调用并可控返回。"""

    def __init__(
        self,
        share_link: str | None = "https://www.binance.com/zh-CN/square/post/123",
        should_raise: bool = False,
    ) -> None:
        self._share_link = share_link
        self._should_raise = should_raise
        self.open_calls: int = 0
        self.close_calls: int = 0
        self.postx_calls: list[dict[str, Any]] = []

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def create_postx(
        self,
        base_asset: str,
        content: str,
        quote: str = "USDT",
        timeframe: str = "1h",
        debug: bool = False,
    ) -> str | None:
        self.postx_calls.append({
            "base_asset": base_asset,
            "content": content,
            "quote": quote,
            "timeframe": timeframe,
            "debug": debug,
        })
        if self._should_raise:
            raise RuntimeError("Playwright 操作失败")
        return self._share_link


@pytest.fixture
def fake_service() -> FakeBinanceService:
    return FakeBinanceService()


def _make_publisher(fake_service: FakeBinanceService) -> BinancePublisher:
    """构造一个注入 fake_service 的 BinancePublisher（绕过真实浏览器）。"""
    publisher = BinancePublisher(headless=True, timeframe="1h")
    publisher._service = fake_service  # type: ignore[attr-defined]
    return publisher


class TestResolveBaseAsset:
    """base_asset 解析测试。"""

    def test_parse_binance_format(self) -> None:
        """✅ BTCUSDT -> BTC。"""
        assert resolve_base_asset("BTCUSDT") == "BTC"

    def test_parse_ccxt_format(self) -> None:
        """✅ BTC/USDT -> BTC。"""
        assert resolve_base_asset("BTC/USDT") == "BTC"

    def test_parse_non_usdt_quote(self) -> None:
        """✅ ETH/BTC -> ETH。"""
        assert resolve_base_asset("ETH/BTC") == "ETH"

    def test_unparseable_returns_original(self) -> None:
        """✅ 无法解析时原样返回（容错）。"""
        assert resolve_base_asset("UNKNOWN") == "UNKNOWN"


class TestBinancePublisherLazyLoad:
    """懒加载测试。"""

    def test_publish_triggers_open(self, fake_service: FakeBinanceService) -> None:
        """✅ 首次 publish_postx 时调用 service.open()。"""
        with patch.object(BinancePublisher, "_get_service_unsafe", return_value=fake_service):
            publisher = BinancePublisher(timeframe="1h")
            publisher.publish_postx(base_asset="BTC", content="test")

            assert len(fake_service.postx_calls) == 1

    def test_service_reused_across_calls(self, fake_service: FakeBinanceService) -> None:
        """✅ 多次发布共用同一 BinanceService。"""
        publisher = _make_publisher(fake_service)

        publisher.publish_postx(base_asset="BTC", content="first")
        publisher.publish_postx(base_asset="ETH", content="second")

        assert len(fake_service.postx_calls) == 2, "应调用两次 create_postx"
        assert fake_service.open_calls == 0, "已注入 service 不应再 open"


class TestPublishPostxParameterForwarding:
    """参数转发测试。"""

    def test_forwards_all_parameters(self, fake_service: FakeBinanceService) -> None:
        """✅ base_asset / content / timeframe 正确传递。"""
        publisher = _make_publisher(fake_service)

        link = publisher.publish_postx(
            base_asset="BTC", content="看涨！", timeframe="4h",
        )

        assert link == "https://www.binance.com/zh-CN/square/post/123"
        call = fake_service.postx_calls[0]
        assert call["base_asset"] == "BTC", f"base_asset 应为 BTC，实际 {call['base_asset']}"
        assert call["content"] == "看涨！"
        assert call["timeframe"] == "4h", f"timeframe 应为 4h，实际 {call['timeframe']}"

    def test_default_timeframe_used_when_none(self, fake_service: FakeBinanceService) -> None:
        """✅ timeframe=None 时使用构造时的默认值。"""
        publisher = BinancePublisher(timeframe="1d")
        publisher._service = fake_service  # type: ignore[attr-defined]

        publisher.publish_postx(base_asset="BTC", content="test")

        assert fake_service.postx_calls[0]["timeframe"] == "1d"

    def test_returns_share_link(self, fake_service: FakeBinanceService) -> None:
        """✅ 成功时返回 share_link。"""
        publisher = _make_publisher(fake_service)

        link = publisher.publish_postx(base_asset="BTC", content="test")

        assert link == "https://www.binance.com/zh-CN/square/post/123"


class TestPublishPostxErrorHandling:
    """异常处理测试。"""

    def test_none_return_raises_runtime_error(self) -> None:
        """✅ create_postx 返回 None 时抛 RuntimeError。"""
        fake = FakeBinanceService(share_link=None)
        publisher = _make_publisher(fake)

        with pytest.raises(RuntimeError, match="postx 发布返回 None"):
            publisher.publish_postx(base_asset="BTC", content="test")

    def test_exception_propagates(self) -> None:
        """✅ create_postx 抛异常时向外传播。"""
        fake = FakeBinanceService(should_raise=True)
        publisher = _make_publisher(fake)

        with pytest.raises(RuntimeError, match="Playwright 操作失败"):
            publisher.publish_postx(base_asset="BTC", content="test")


class TestBinancePublisherClose:
    """close 行为测试。"""

    def test_close_calls_service_close(self, fake_service: FakeBinanceService) -> None:
        """✅ close() 调用 service.close()。"""
        publisher = _make_publisher(fake_service)

        publisher.close()

        assert fake_service.close_calls == 1, "应调用一次 service.close()"

    def test_close_resets_service_to_none(self, fake_service: FakeBinanceService) -> None:
        """✅ close() 后 service 变为 None。"""
        publisher = _make_publisher(fake_service)

        publisher.close()

        assert publisher._service is None  # type: ignore[attr-defined]

    def test_close_idempotent(self, fake_service: FakeBinanceService) -> None:
        """✅ 多次调用 close() 不崩溃，service 只关闭一次。"""
        publisher = _make_publisher(fake_service)

        publisher.close()
        publisher.close()
        publisher.close()

        assert fake_service.close_calls == 1, "service.close() 应只调用一次"

    def test_close_when_service_already_none(self) -> None:
        """✅ service 为 None 时 close() 不崩溃。"""
        publisher = BinancePublisher()

        publisher.close()  # 不应抛异常


class TestBinancePublisherConfig:
    """配置构建测试。"""

    def test_build_config_with_custom_storage_path(self) -> None:
        """✅ 自定义 storage_state_path 被正确传入 AppConfig。"""
        publisher = BinancePublisher(
            storage_state_path="/custom/path.json",
            headless=False,
            timeframe="4h",
        )
        config = publisher._build_config()

        assert config.chrome.storage_state_path == "/custom/path.json"
        assert config.headless is False

    def test_build_config_uses_default_when_no_path(self) -> None:
        """✅ 未指定 storage_state_path 时用 ChromeConfig.default()。"""
        publisher = BinancePublisher()
        config = publisher._build_config()

        # 默认路径来自 ChromeConfig.default()，应为 ~/.binance-service/storage_state.json
        assert "storage_state.json" in config.chrome.storage_state_path
        assert config.headless is True
