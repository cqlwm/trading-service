"""测试 BinancePublisher 的纯函数与配置加载。

注：发布管道（enqueue/回调/线程亲和/浏览器释放）的测试在
test_publisher_async.py 中。本文件只覆盖不依赖发布管道的部分：
- resolve_base_asset 解析
- 配置加载（AppConfig 各子段、~ 展开、文件缺失、构造参数）
"""
from __future__ import annotations

import pytest

from trading_service.content.publisher import BinancePublisher, resolve_base_asset

# binance-service 真实配置文件，用于配置加载测试（路径与 config.local.yaml 一致）
BINANCE_CONFIG_PATH = "/Users/li/projects/binance-service/config.yaml"


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
