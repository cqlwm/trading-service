"""架构契约测试 - 防止忘记接口约定被破坏。

每次运行所有测试时，这些测试会自动验证所有关键约定没有被违反。
"""
from __future__ import annotations

import inspect

from trading_service.pickers import (
    AlphaTokenSource,
    ISymbolFilter,
    ISymbolPicker,
    ISymbolSource,
    SelectionPipeline,
    StaticListSymbolPicker,
    SymbolInfo,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
    ITechnicalAnalyzer,
)


class TestSymbolPickerContracts:
    """ISymbolPicker 接口契约测试（策略层契约）。"""

    def test_pick_method_must_be_async(self) -> None:
        """✅ ISymbolPicker.pick() 必须是 async！

        这是一个常见陷阱 - 忘记继承 ISymbolPicker 后写了同步 pick() 方法。
        """
        assert inspect.iscoroutinefunction(ISymbolPicker.pick), \
            "❌ ISymbolPicker.pick() 必须是 async 方法！"

    def test_all_pickers_have_async_pick(self) -> None:
        """✅ 所有 ISymbolPicker 实现类的 pick 都必须是 async。"""
        all_pickers = [
            StaticListSymbolPicker,
            SelectionPipeline,
        ]

        for picker_cls in all_pickers:
            assert inspect.iscoroutinefunction(picker_cls.pick), \
                f"❌ {picker_cls.__name__}.pick() 必须是 async 方法！"

    def test_symbol_info_has_all_required_fields(self) -> None:
        """✅ SymbolInfo 必须包含策略框架依赖的字段。"""
        required_fields = [
            "symbol",
            "price",
            "volume_24h",
            "market_cap",
            "price_change_pct_24h",
        ]

        info = SymbolInfo(symbol="TEST")

        for field in required_fields:
            assert hasattr(info, field), \
                f"❌ SymbolInfo 缺少必须字段: {field}"


class TestPipelineContracts:
    """管道抽象契约测试（组装层契约）。"""

    def test_source_fetch_must_be_async(self) -> None:
        """✅ ISymbolSource.fetch() 必须是 async。"""
        assert inspect.iscoroutinefunction(ISymbolSource.fetch), \
            "❌ ISymbolSource.fetch() 必须是 async 方法！"

    def test_filter_apply_must_be_async(self) -> None:
        """✅ ISymbolFilter.apply() 必须是 async。"""
        assert inspect.iscoroutinefunction(ISymbolFilter.apply), \
            "❌ ISymbolFilter.apply() 必须是 async 方法！"

    def test_pipeline_implements_symbol_picker(self) -> None:
        """✅ SelectionPipeline 必须实现 ISymbolPicker（对策略层透明）。"""
        # 用最小可构造参数实例化（source 给一个内存 stub）
        from trading_service.pickers.base import SymbolInfo as _Info

        class _StubSource(ISymbolSource):
            async def fetch(self) -> list[_Info]:
                return []

        pipeline = SelectionPipeline(source=_StubSource())
        assert isinstance(pipeline, ISymbolPicker), \
            "❌ SelectionPipeline 必须实现 ISymbolPicker，策略才能无感使用"

    def test_alpha_source_implements_symbol_source(self) -> None:
        """✅ AlphaTokenSource 必须实现 ISymbolSource。"""
        # 用 stub client 构造，避免触发真实网络
        from unittest.mock import MagicMock

        source = AlphaTokenSource(client=MagicMock())  # type: ignore[arg-type]
        assert isinstance(source, ISymbolSource)

    def test_technical_filter_implements_symbol_filter(self) -> None:
        """✅ TechnicalAnalysisFilter 必须实现 ISymbolFilter。"""
        from unittest.mock import MagicMock

        f = TechnicalAnalysisFilter(
            analyzer=TechnicalAnalyzer(), client=MagicMock()  # type: ignore[arg-type]
        )
        assert isinstance(f, ISymbolFilter)


class TestTechnicalAnalyzerContracts:
    """ITechnicalAnalyzer 接口契约测试。"""

    def test_detect_200sma_signal_is_defined(self) -> None:
        """✅ ITechnicalAnalyzer 必须定义 detect_200sma_signal 方法。"""
        assert hasattr(ITechnicalAnalyzer, "detect_200sma_signal"), \
            "❌ ITechnicalAnalyzer 必须定义 detect_200sma_signal 抽象方法"

    def test_technical_analyzer_implements_interface(self) -> None:
        """✅ TechnicalAnalyzer 必须实现 ITechnicalAnalyzer 接口。"""
        analyzer: ITechnicalAnalyzer = TechnicalAnalyzer()
        assert isinstance(analyzer, ITechnicalAnalyzer), \
            "❌ TechnicalAnalyzer 必须实现 ITechnicalAnalyzer 接口"


class TestModuleOrganization:
    """模块组织架构约定。"""

    def test_no_should_not_create_symbol_picker_in_strategies(self) -> None:
        """❌ 不允许在 strategies/ 目录下创建 symbol_picker.py！

        picker 统一放在 trading_service/pickers/
        """
        import os
        sp_path = os.path.join(
            os.path.dirname(__file__),
            "../../trading_service/strategies/symbol_picker.py",
        )
        assert not os.path.exists(sp_path), \
            "❌ 发现旧文件: trading_service/strategies/symbol_picker.py\n" \
            "   -> 所有选币器应该统一放在 trading_service/pickers/"

    def test_pickers_export_all_in_pickers_module(self) -> None:
        """✅ 所有 picker 类应该能从 pickers 模块统一导出。"""
        from trading_service.pickers import __all__

        expected = [
            # 核心契约
            "ISymbolPicker",
            "SymbolInfo",
            "StaticListSymbolPicker",
            # 管道抽象
            "ISymbolSource",
            "ISymbolFilter",
            "SelectionPipeline",
            # 数据源
            "AlphaTokenSource",
            # 技术分析
            "ITechnicalAnalyzer",
            "TechnicalAnalyzer",
            "TechnicalAnalysisFilter",
            "CrossSignal",
        ]

        for name in expected:
            assert name in __all__, f"❌ {name} 应该在 __all__ 中导出"

    def test_simple_alpha_symbol_picker_removed(self) -> None:
        """✅ 旧的 SimpleAlphaSymbolPicker 已被管道化重构移除。

        选币器与技术分析已解耦：
        - 选币 -> AlphaTokenSource（ISymbolSource）
        - 技术分析 -> TechnicalAnalysisFilter（ISymbolFilter）
        - 编排 -> SelectionPipeline（ISymbolPicker）
        """
        import trading_service.pickers as pickers

        assert not hasattr(pickers, "SimpleAlphaSymbolPicker"), \
            "❌ SimpleAlphaSymbolPicker 应已移除，改用 AlphaTokenSource + SelectionPipeline"
