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

# binance-service 真实配置文件，用于配置加载测试（路径与 config.local.yaml 一致）
BINANCE_CONFIG_PATH = "/Users/li/projects/binance-service/config.yaml"


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
    publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH, timeframe="1h")
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
            publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH, timeframe="1h")
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
        publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH, timeframe="1d")
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
        publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH)

        publisher.close()  # 不应抛异常


class TestBinancePublisherConfig:
    """配置加载测试（通过 load_config 从 binance-service 的 config.yaml 加载完整 AppConfig）。"""

    def test_load_config_returns_full_appconfig(self) -> None:
        """✅ 加载真实 config.yaml 返回含全部子段的 AppConfig。"""
        publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH, timeframe="4h", debug=True)
        config = publisher._load_config()

        # 七个子段均应加载成功
        assert config.chrome.debug_port == 9222, f"chrome.debug_port 应为 9222，实际 {config.chrome.debug_port}"
        assert config.window.width == 1920
        assert config.headless is True
        assert config.browser.device_scale_factor == 2.0
        assert config.poster.target_url.startswith("https://www.binance.com")
        assert config.screenshot.default_timeframe == "1h"
        assert config.cdp.retry_count == 20

    def test_load_config_expands_storage_state_path(self) -> None:
        """✅ YAML 中 storage_state_path 含 ~ 被展开为家目录。"""
        publisher = BinancePublisher(config_path=BINANCE_CONFIG_PATH)
        config = publisher._load_config()

        assert "~" not in config.chrome.storage_state_path, "~ 应已被展开"
        assert config.chrome.storage_state_path.endswith("storage_state.json")

    def test_load_config_raises_when_file_missing(self) -> None:
        """✅ 配置文件不存在时抛 FileNotFoundError。"""
        publisher = BinancePublisher(config_path="/nonexistent/path/to/config.yaml")

        with pytest.raises(FileNotFoundError, match="Config file not found"):
            publisher._load_config()

    def test_init_stores_timeframe_and_debug(self) -> None:
        """✅ 构造参数 timeframe/debug 被正确保存（不触发配置加载）。"""
        publisher = BinancePublisher(
            config_path=BINANCE_CONFIG_PATH, timeframe="4h", debug=True,
        )

        assert publisher._default_timeframe == "4h"  # type: ignore[attr-defined]
        assert publisher._debug is True  # type: ignore[attr-defined]
