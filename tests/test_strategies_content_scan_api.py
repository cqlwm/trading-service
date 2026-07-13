"""content_scan 策略 API 端点测试。

验证 GET /api/strategies/content-scan/status 和
POST /api/strategies/content-scan/execute 端点。

采用 httpx.AsyncClient + ASGITransport 直接打 ASGI app，绕过 app.py 的
lifespan（lifespan 会启动真实 scheduler，副作用过大），通过
app.dependency_overrides 注入内存版策略与调度器。
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from trading_service.app import app
from trading_service.api.deps import get_content_scan_strategy, get_strategy_scheduler
from trading_service.exchange import MockExchange
from trading_service.scheduler import StrategyScheduler
from trading_service.strategies.content_scan import ContentScanConfig, ContentScanStrategy
from trading_service.pickers import ISymbolPicker


class EmptyPicker(ISymbolPicker):
    """空选币器，避免真实网络请求。"""

    async def pick(self) -> list[Any]:
        return []


def _make_strategy(exchange: MockExchange) -> ContentScanStrategy:
    """构造内存版 content_scan 策略。"""
    return ContentScanStrategy(
        exchange=exchange,
        config=ContentScanConfig(),
        symbol_picker=EmptyPicker(),
    )


def _make_scheduler(exchange: MockExchange, strategy: ContentScanStrategy) -> StrategyScheduler:
    """构造内存版调度器（不 start，仅用于 status/execute 查询）。"""
    repo = exchange.db  # type: ignore[attr-defined]
    return StrategyScheduler(repo=repo, strategies=[strategy])


@pytest.fixture
def client_setup(exchange: MockExchange) -> tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]:
    """组装测试用 client：覆盖依赖 + ASGITransport（不触发 lifespan）。

    返回 (client, strategy, scheduler)，方便测试中进一步断言。
    """
    strategy = _make_strategy(exchange)
    scheduler = _make_scheduler(exchange, strategy)

    app.dependency_overrides[get_content_scan_strategy] = lambda: strategy
    app.dependency_overrides[get_strategy_scheduler] = lambda: scheduler

    transport = ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, strategy, scheduler


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    """每个测试后清理 dependency_overrides，避免污染其他测试。"""
    yield
    app.dependency_overrides.clear()


class TestContentScanStatusEndpoint:
    """GET /api/strategies/content-scan/status 端点。"""

    @pytest.mark.asyncio
    async def test_status_returns_strategy_metadata(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 正常路径：返回 strategy/cron/type/config 字段。"""
        client, _, _ = client_setup
        resp = await client.get("/api/strategies/content-scan/status")

        assert resp.status_code == 200, f"状态码应为 200，实际 {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["strategy"] == "content_scan", f"strategy 应为 content_scan，实际 {data['strategy']}"
        assert data["cron"] == "0 */10 * * * *", f"cron 应为每10分钟，实际 {data['cron']}"
        assert data["type"] == "content", f"type 应为 content，实际 {data['type']}"

    @pytest.mark.asyncio
    async def test_status_includes_config_top_n(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 正常路径：status 包含 config.top_n。"""
        client, _, _ = client_setup
        resp = await client.get("/api/strategies/content-scan/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "config" in data, "应包含 config 字段"
        assert data["config"]["top_n"] == 20, f"top_n 默认应为 20，实际 {data['config']['top_n']}"

    @pytest.mark.asyncio
    async def test_status_includes_schedule(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 正常路径：status 附加 schedule 字段（调度信息）。"""
        client, _, _ = client_setup
        resp = await client.get("/api/strategies/content-scan/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "schedule" in data, "应包含 schedule 字段"
        schedule = data["schedule"]
        assert schedule is not None
        assert schedule["strategy_name"] == "content_scan"
        assert "running" in schedule
        assert "cron" in schedule
        assert "next_run_at" in schedule
        assert "last_run_at" in schedule

    @pytest.mark.asyncio
    async def test_status_has_no_position_fields(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 内容型策略不持仓：status 不含 open_positions/total_positions。"""
        client, _, _ = client_setup
        resp = await client.get("/api/strategies/content-scan/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "open_positions" not in data, "content_scan 不应包含 open_positions"
        assert "total_positions" not in data, "content_scan 不应包含 total_positions"


class TestContentScanExecuteEndpoint:
    """POST /api/strategies/content-scan/execute 端点。"""

    @pytest.mark.asyncio
    async def test_execute_returns_ok_response(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 正常路径：execute 返回标准响应结构。"""
        client, _, _ = client_setup
        resp = await client.post("/api/strategies/content-scan/execute")

        assert resp.status_code == 200, f"状态码应为 200，实际 {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "ok", f"status 应为 ok，实际 {data['status']}"
        assert data["strategy"] == "content_scan", f"strategy 应为 content_scan，实际 {data['strategy']}"
        assert "execution_id" in data, "应包含 execution_id"
        assert isinstance(data["actions"], list), "actions 应为列表"
        assert data["action_count"] == len(data["actions"]), "action_count 应等于 actions 长度"

    @pytest.mark.asyncio
    async def test_execute_with_no_signals_returns_empty_actions(
        self, client_setup: tuple[httpx.AsyncClient, ContentScanStrategy, StrategyScheduler]
    ) -> None:
        """✅ 空值场景：无候选币时 execute 返回空 actions。"""
        client, _, _ = client_setup
        resp = await client.post("/api/strategies/content-scan/execute")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action_count"] == 0, "无信号时 action_count 应为 0"
        assert data["actions"] == [], "无信号时 actions 应为空列表"
