"""选币管道：source 产出候选 -> filters 依次增强/过滤。

将"选币（数据从哪来）"与"分析（怎么处理）"解耦为两个独立阶段，
让技术分析等增强逻辑成为可组合的 filter，而非焊死在选币器里。

层次：
- ISymbolSource : 数据来源（生成器语义，fetch 产出 list[SymbolInfo]）
- ISymbolFilter : 处理阶段（转换器语义，apply 接收并返回 list[SymbolInfo]）
- SelectionPipeline : 实现 ISymbolPicker，对策略层透明地串联 source + filters
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from trading_service.pickers.base import ISymbolPicker, SymbolInfo


class ISymbolSource(ABC):
    """数据源接口：产出候选 SymbolInfo 列表（从无到有）。"""

    @abstractmethod
    async def fetch(self) -> list[SymbolInfo]:
        """获取候选币种列表。"""
        ...


class ISymbolFilter(ABC):
    """过滤器接口：接收并转换 SymbolInfo 列表。

    可以是纯增强（回填字段、不改变数量），也可以是过滤（丢弃部分元素）。
    """

    @abstractmethod
    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        """对候选列表进行处理，返回处理后的列表。"""
        ...


class SelectionPipeline(ISymbolPicker):
    """选币管道：source + filters 串联，对外暴露 ISymbolPicker.pick()。

    策略层无感知——仍然只调 pick()、读 list[SymbolInfo]。
    """

    def __init__(
        self,
        source: ISymbolSource,
        filters: list[ISymbolFilter] | None = None,
    ) -> None:
        self.source = source
        self.filters = filters if filters is not None else []

    async def pick(self) -> list[SymbolInfo]:
        """依次执行 source.fetch() 与所有 filter.apply()，返回最终列表。"""
        infos = await self.source.fetch()
        for f in self.filters:
            infos = await f.apply(infos)
        return infos
