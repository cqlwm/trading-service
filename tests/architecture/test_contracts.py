"""架构契约测试 - 防止忘记接口约定被破坏。

每次运行所有测试时，这些测试会自动验证所有关键约定没有被违反。
"""
from __future__ import annotations

import inspect
import pytest

from trading_service.pickers import (
    ISymbolPicker,
    SimpleAlphaSymbolPicker,
    StaticListSymbolPicker,
    SymbolInfo,
)


class TestSymbolPickerContracts:
    """ISymbolPicker 接口契约测试。"""

    def test_pick_method_must_be_async(self) -> None:
        """✅ ISymbolPicker.pick() 必须是 async！

        这是一个常见陷阱 - 忘记继承 ISymbolPicker 后写了同步 pick() 方法。
        """
        assert inspect.iscoroutinefunction(ISymbolPicker.pick), \
            "❌ ISymbolPicker.pick() 必须是 async 方法！"

    def test_all_pickers_have_async_pick(self) -> None:
        """✅ 所有 ISymbolPicker 实现类的 pick 都必须是 async。"""
        all_pickers = [
            SimpleAlphaSymbolPicker,
            StaticListSymbolPicker,
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
            "ISymbolPicker",
            "SymbolInfo",
            "StaticListSymbolPicker",
            "SimpleAlphaSymbolPicker",
            "TechnicalAnalyzer",
            "CrossSignal",
        ]

        for name in expected:
            assert name in __all__, f"❌ {name} 应该在 __all__ 中导出"
