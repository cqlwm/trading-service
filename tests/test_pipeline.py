"""测试 SelectionPipeline 编排器（TDD 红阶段）。

管道模式：source 产出候选 -> filters 依次增强/过滤 -> 策略消费。
- ISymbolSource.fetch()  : 数据从哪来（生成器语义，从无到有）
- ISymbolFilter.apply()  : 怎么处理（转换器语义，接收并返回 list[SymbolInfo]）
- SelectionPipeline      : 实现 ISymbolPicker，对策略层透明

测试覆盖 7 类场景：正常路径、边界、隔离、优先级、幂等、空值、事务一致性。
全部使用内存实现，零网络、毫秒级运行。
"""
from __future__ import annotations

import inspect

import pytest

from trading_service.pickers import ISymbolPicker, SymbolInfo
from trading_service.pickers.pipeline import (
    ISymbolFilter,
    ISymbolSource,
    SelectionPipeline,
)


class FakeSymbolSource(ISymbolSource):
    """内存版数据源 - 返回固定的 SymbolInfo 列表。"""

    def __init__(self, symbols: list[SymbolInfo]) -> None:
        self.symbols = symbols

    async def fetch(self) -> list[SymbolInfo]:
        return [SymbolInfo(symbol=s.symbol) for s in self.symbols]  # 返回副本，隔离副作用


class TaggingFilter(ISymbolFilter):
    """内存版过滤器 - 给每个 SymbolInfo 打标记（验证字段增强）。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        for info in infos:
            info.base_asset = self.tag
        return infos


class DropBySymbolFilter(ISymbolFilter):
    """内存版过滤器 - 丢弃指定 symbol（验证过滤能力）。"""

    def __init__(self, drop_symbol: str) -> None:
        self.drop_symbol = drop_symbol

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        return [i for i in infos if i.symbol != self.drop_symbol]


class RecordingFilter(ISymbolFilter):
    """记录被处理过的 symbol 序列，用于验证多过滤器执行顺序。"""

    def __init__(self, label: str, log: list[str]) -> None:
        self.label = label
        self.log = log

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        self.log.append(f"{self.label}:{','.join(i.symbol for i in infos)}")
        return infos


def make_info(symbol: str) -> SymbolInfo:
    return SymbolInfo(symbol=symbol)


class TestPipelineInterfaces:
    """接口契约测试。"""

    def test_source_fetch_must_be_async(self) -> None:
        """✅ ISymbolSource.fetch() 必须是 async。"""
        assert inspect.iscoroutinefunction(ISymbolSource.fetch), \
            "❌ ISymbolSource.fetch() 必须是 async 方法！"

    def test_filter_apply_must_be_async(self) -> None:
        """✅ ISymbolFilter.apply() 必须是 async。"""
        assert inspect.iscoroutinefunction(ISymbolFilter.apply), \
            "❌ ISymbolFilter.apply() 必须是 async 方法！"

    def test_pipeline_implements_symbol_picker(self) -> None:
        """✅ SelectionPipeline 必须实现 ISymbolPicker 接口（对策略层透明）。"""
        pipeline = SelectionPipeline(source=FakeSymbolSource([]))
        assert isinstance(pipeline, ISymbolPicker), \
            "❌ SelectionPipeline 必须实现 ISymbolPicker，策略才能无感使用"

    def test_pipeline_pick_is_async(self) -> None:
        """✅ SelectionPipeline.pick() 必须是 async（继承自 ISymbolPicker 契约）。"""
        assert inspect.iscoroutinefunction(SelectionPipeline.pick), \
            "❌ SelectionPipeline.pick() 必须是 async 方法！"


class TestPipelineHappyPath:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_source_only_no_filters(self) -> None:
        """正常路径：无 filter 时，pick() 直接返回 source 结果。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT"), make_info("BBBUSDT")]),
        )
        result = await pipeline.pick()
        assert [i.symbol for i in result] == ["AAAUSDT", "BBBUSDT"]

    @pytest.mark.asyncio
    async def test_single_filter_enriches_fields(self) -> None:
        """正常路径：单个 filter 增强字段后返回。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT")]),
            filters=[TaggingFilter("tagged")],
        )
        result = await pipeline.pick()
        assert len(result) == 1
        assert result[0].base_asset == "tagged", "filter 应已增强 base_asset 字段"

    @pytest.mark.asyncio
    async def test_single_filter_can_drop(self) -> None:
        """正常路径：source[A,B,C] + filter(丢B) -> [A,C]。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([
                make_info("AAAUSDT"), make_info("BBBUSDT"), make_info("CCCUSDT"),
            ]),
            filters=[DropBySymbolFilter("BBBUSDT")],
        )
        result = await pipeline.pick()
        assert [i.symbol for i in result] == ["AAAUSDT", "CCCUSDT"]


class TestPipelineMultipleFilters:
    """多过滤器场景（优先级/顺序）。"""

    @pytest.mark.asyncio
    async def test_filters_applied_in_order(self) -> None:
        """优先级：多 filter 按声明顺序依次应用。"""
        log: list[str] = []
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT"), make_info("BBBUSDT")]),
            filters=[
                RecordingFilter("first", log),
                RecordingFilter("second", log),
            ],
        )
        await pipeline.pick()
        assert log == ["first:AAAUSDT,BBBUSDT", "second:AAAUSDT,BBBUSDT"], \
            f"过滤器应按顺序执行，实际 {log}"

    @pytest.mark.asyncio
    async def test_filter_chain_passes_intermediate_result(self) -> None:
        """组合逻辑：前一个 filter 丢弃的元素不进入下一个 filter。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([
                make_info("AAAUSDT"), make_info("BBBUSDT"), make_info("CCCUSDT"),
            ]),
            filters=[
                DropBySymbolFilter("BBBUSDT"),
                TaggingFilter("kept"),
            ],
        )
        result = await pipeline.pick()
        assert [i.symbol for i in result] == ["AAAUSDT", "CCCUSDT"]
        assert all(i.base_asset == "kept" for i in result), "剩下的应被第二个 filter 增强"


class TestPipelineBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_empty_source_returns_empty(self) -> None:
        """边界：空 source -> []。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([]),
            filters=[TaggingFilter("x")],
        )
        result = await pipeline.pick()
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_default_empty(self) -> None:
        """边界：filters=None 时按空链处理，等价于直接返回 source。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT")]),
            filters=None,
        )
        result = await pipeline.pick()
        assert [i.symbol for i in result] == ["AAAUSDT"]

    @pytest.mark.asyncio
    async def test_empty_filters_list(self) -> None:
        """空值：显式传空 filter 列表也不报错。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT")]),
            filters=[],
        )
        result = await pipeline.pick()
        assert len(result) == 1


class TestPipelineIsolation:
    """隔离机制测试。"""

    @pytest.mark.asyncio
    async def test_two_pipelines_independent(self) -> None:
        """隔离：两个 pipeline 互不影响。"""
        p1 = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT")]),
            filters=[DropBySymbolFilter("AAAUSDT")],
        )
        p2 = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT")]),
        )
        r1 = await p1.pick()
        r2 = await p2.pick()
        assert r1 == [], "p1 应丢弃 AAAUSDT"
        assert [i.symbol for i in r2] == ["AAAUSDT"], "p2 应保留 AAAUSDT"


class TestPipelineIdempotency:
    """幂等性测试。"""

    @pytest.mark.asyncio
    async def test_two_picks_consistent(self) -> None:
        """幂等性：同一 pipeline 两次 pick 结果一致。"""
        pipeline = SelectionPipeline(
            source=FakeSymbolSource([make_info("AAAUSDT"), make_info("BBBUSDT")]),
            filters=[DropBySymbolFilter("BBBUSDT")],
        )
        r1 = await pipeline.pick()
        r2 = await pipeline.pick()
        assert [i.symbol for i in r1] == [i.symbol for i in r2] == ["AAAUSDT"]
