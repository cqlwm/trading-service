"""数据访问层 - Repository

架构：
    abc.py              - 抽象基类接口定义
    sqlalchemy_impl.py  - SQLAlchemy 实现
    models/             - ORM 模型目录
        base.py         - Base 基类
        position.py     - 持仓模型
        order.py        - 订单模型
        signal.py       - 信号模型
"""

# 数据记录类（供业务层使用）
from trading_service.repository.abc import (
    OrderRecord,
    PositionRecord,
    SignalRecord,
    StrategyExecutionRecord,
    StrategyScheduleRecord,
)

# Repository 抽象接口
from trading_service.repository.abc import TradingRepository

# SQLAlchemy 实现
from trading_service.repository.sqlalchemy_impl import SqlalchemyTradingStore

# ORM 模型（供迁移和数据层内部使用）
from trading_service.repository.models import (
    Base,
    OrderModel,
    PositionModel,
    SignalModel,
    StrategyExecutionModel,
    StrategyScheduleModel,
)

__all__ = [
    # 数据记录类
    "PositionRecord",
    "OrderRecord",
    "SignalRecord",
    "StrategyScheduleRecord",
    "StrategyExecutionRecord",
    # 抽象接口
    "TradingRepository",
    # SQLAlchemy 实现
    "SqlalchemyTradingStore",
    # ORM 模型
    "Base",
    "PositionModel",
    "OrderModel",
    "SignalModel",
    "StrategyScheduleModel",
    "StrategyExecutionModel",
]
