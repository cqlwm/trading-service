# 系统架构

## 1. 分层架构

### 整体分层图

```mermaid
graph TB
    subgraph "表现层 (Presentation)"
        API[FastAPI REST API]
        DOCS[Swagger UI / ReDoc]
    end

    subgraph "业务逻辑层 (Business Logic)"
        EXCHANGE[MockExchange<br/>业务编排器]
        TIMELINE[Timeline Service]
        STORY[Trade Story Service]
    end

    subgraph "策略引擎层 (Strategy Engine)"
        STRATEGY[Strategy 抽象基类]
        MARTINGALE[MartingaleStrategy]
        MICROCAP[MicroCapStrategy]
        PICKER[SymbolPicker<br/>币种选择器]
    end

    subgraph "数据访问层 (Data Access)"
        STORE[TradingStore 抽象接口]
        SQLITE[SqlalchemyTradingStore (repository/sqlalchemy_impl.py)]
    end

    subgraph "基础设施层 (Infrastructure)"
        DB[(SQLite 数据库)]
        HTTP[HTTP Client<br/>News Service]
        LOG[Logging 系统]
        CFG[Settings 配置]
    end

    API --> EXCHANGE
    API --> STRATEGY
    
    EXCHANGE --> STORE
    EXCHANGE --> TIMELINE
    EXCHANGE --> STORY
    
    STRATEGY --> EXCHANGE
    STRATEGY --> PICKER
    
    STORE --> SQLITE
    SQLITE --> DB
    
    STRATEGY --> HTTP
    EXCHANGE --> HTTP
    
    CFG -.-> API
    CFG -.-> STRATEGY
    LOG -.-> EXCHANGE
```

### 各层职责

| 层级 | 职责 | 核心模块 |
|------|------|----------|
| **表现层** | 处理 HTTP 请求、路由分发、参数校验、响应格式化 | `app.py`, `api/*.py` |
| **业务逻辑层** | 核心业务规则、领域模型、交易编排 | `exchange.py` |
| **策略引擎层** | 交易策略实现、币种选择、执行调度 | `strategies/*.py` |
| **数据访问层** | 数据持久化抽象、Repository 模式 | `repository/` |
| **基础设施层** | 数据库、HTTP 客户端、日志、配置 | `config.py`, SQLite, Alembic |

---

## 2. 目录结构

```
trading_service/
├── __init__.py
├── app.py                  # FastAPI 应用入口
├── config.py               # 配置管理 (Pydantic Settings + YAML)
├── types.py                # 枚举类型定义
├── exchange.py             # 业务逻辑核心 - MockExchange
├── migration_check.py      # 启动时数据库迁移校验
│
├── api/                    # API 路由层
│   ├── __init__.py
│   ├── deps.py             # 依赖注入
│   ├── positions.py        # 持仓管理 API
│   ├── orders.py           # 订单查询 API
│   ├── signals.py          # 信号查询 API
│   ├── timeline.py         # 时间线 + 交易故事 API
│   └── strategies.py       # 策略执行 API
│
├── repository/             # 数据访问层 - Repository 模式
│   ├── __init__.py         # 对外统一导出
│   ├── abc.py              # 抽象基类接口定义
│   ├── sqlalchemy_impl.py  # SQLAlchemy ORM 实现
│   └── models/             # ORM 模型目录
│       ├── __init__.py
│       ├── base.py         # SQLAlchemy Declarative Base
│       ├── position.py     # 持仓模型
│       ├── order.py        # 订单模型
│       └── signal.py       # 信号模型
│
├── strategies/             # 策略引擎层
│   ├── __init__.py
│   ├── base.py             # Strategy 抽象基类
│   ├── martingale.py       # 马丁格尔策略
│   ├── micro_cap.py        # 小市值策略
│   └── symbol_picker.py    # 币种选择器
│
├── utils/                  # 工具函数
│   └── symbol.py           # 交易对工具类
│
migrations/                 # Alembic 数据库迁移脚本
├── versions/               # 版本化迁移脚本
└── env.py                  # Alembic 环境配置
│
├── strategies/             # 策略引擎层
│   ├── __init__.py
│   ├── base.py             # Strategy 抽象基类 + StrategyConfig
│   ├── martingale.py       # 马丁格尔策略
│   ├── micro_cap.py        # 微市值策略
│   └── symbol_picker.py    # 币种选择器接口
│
└── utils/
    ├── __init__.py
    └── symbol.py           # Symbol 工具函数
```

---

## 3. 核心设计模式

### 3.1 Repository 模式 (数据访问层)

**架构演进**：从简单 SQLite 实现升级为标准 Repository 模式

```python
# repository/abc.py - 抽象接口定义
class TradingRepository(ABC):
    @abstractmethod
    def save_position(self, position: PositionRecord) -> None: ...
    
    @abstractmethod
    def get_position(self, position_id: str) -> PositionRecord | None: ...
    
    @abstractmethod
    def list_positions(self, symbol: str | None = None) -> list[PositionRecord]: ...
```

```python
# repository/sqlalchemy_impl.py - SQLAlchemy 实现
class SqlalchemyTradingStore(TradingRepository):
    # 具体 ORM 实现
    # ...
```

**目的与收益**：
- **依赖倒置**：业务层只依赖抽象接口，不依赖具体 ORM
- **可测试性**：可轻松 Mock 接口进行单元测试
- **可替换性**：未来换 PostgreSQL/MySQL 只需新增实现类
- **可维护性**：ORM 模型拆分到独立文件，便于扩展
- **版本管理**：Alembic 迁移系统管理数据库 Schema 变更

**使用方式**：
```python
# 业务层只依赖抽象接口
from trading_service.repository import (
    TradingRepository,  # 抽象接口
    PositionRecord,     # 纯数据类
    OrderRecord,
    SignalRecord,
)

# 仅在依赖注入时使用具体实现
db = SqlalchemyTradingStore(db_path)
exchange = MockExchange(db=db)
```

### 3.2 Strategy 模式 (策略引擎)

```python
class Strategy(ABC):
    def __init__(self, exchange: MockExchange, config: StrategyConfig, symbol_picker: ISymbolPicker):
        self.exchange = exchange
        self.config = config
        self.symbol_picker = symbol_picker

    @abstractmethod
    async def execute(self) -> None: ...
    
    @abstractmethod
    def get_status(self) -> dict: ...
```

**目的**：
- 统一策略接口，便于新增策略
- 策略可独立配置和测试
- 支持运行时切换策略

### 3.3 依赖注入 (DI)

**位置**：`api/deps.py`

```python
def get_db() -> SqlalchemyTradingStore (repository/sqlalchemy_impl.py): ...
def get_exchange(db: SqlalchemyTradingStore (repository/sqlalchemy_impl.py) = Depends(get_db)) -> MockExchange: ...
def get_strategy(name: str, exchange: MockExchange = Depends(get_exchange)) -> Strategy: ...
```

**目的**：
- 各层解耦，依赖可替换
- 便于单元测试
- FastAPI 原生支持，生命周期管理清晰

---

## 4. 技术栈详情

| 技术 | 版本 | 用途 | 选型理由 |
|------|------|------|----------|
| **Python** | 3.12+ | 开发语言 | 生态丰富，数据科学/量化友好 |
| **FastAPI** | 0.115+ | Web 框架 | 高性能、异步支持、自动文档、类型安全 |
| **Pydantic** | 2.x | 数据验证 | 类型安全、配置管理 |
| **Pydantic Settings** | 2.x | 配置管理 | 环境变量加载、类型安全 |
| **SQLite3** | 内置 | 数据库 | 轻量、零配置、适合单实例部署 |
| **uv** | 最新 | 包管理 | 快速、现代、替代 pip/poetry |
| **pytest** | 最新 | 测试框架 | 成熟、插件丰富 |
| **logging** | 标准库 | 日志 | 内置、无需额外依赖 |

---

## 5. 部署架构

```mermaid
graph LR
    subgraph "Host Machine"
        subgraph "Trading Service (8001)"
            TS[FastAPI<br/>uvicorn]
            TSD[(SQLite<br/>news.db)]
        end
        
        subgraph "News Service (8000)"
            NS[FastAPI<br/>uvicorn]
            NSD[(SQLite<br/>news.db)]
        end
    end
    
    USER[Client] -->|HTTP API| TS
    USER -->|HTTP API| NS
    
    TS -->|HTTP| NS
    NS -->|HTTP| TS
    
    TS -.-> TSD
    NS -.-> NSD
    TSD == NSD
```

### 部署要点

1. **共享数据库**：两个服务使用同一份 SQLite 文件
   - 路径：`~/projects/news-service/news.db`
   - 表命名空间：`trading_*` 归属 Trading Service

2. **端口约定**：
   - Trading Service: 8001
   - News Service: 8000

3. **双向通信**：
   - Trading Service → News Service: 拉取市场数据、K线、币种排名
   - News Service → Trading Service: 触发策略执行

---

## 6. 关键设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| **数据库** | SQLite vs PostgreSQL | SQLite | 轻量、零运维、单实例足够 |
| **数据库共享** | 独立 DB vs 共享 DB | 共享 DB | 避免分布式事务、简化部署 |
| **策略调度** | 内置 vs 外部调度器 | 内置 (API 触发) | 灵活，由 News Service 定时调用 |
| **交易所接入** | 真实 API vs Mock | Mock 优先 | 便于开发测试，真实接入可替换 |
| **异步设计** | 同步 vs 异步 | 异步策略执行 | 策略可能耗时，不阻塞 API |

---

## 7. 扩展点

### 7.1 新增策略

1. 继承 `Strategy` 基类
2. 实现 `execute()` 和 `get_status()`
3. 在 `api/strategies.py` 注册路由
4. 在 `api/deps.py` 添加工厂函数

### 7.2 替换数据库

1. 实现 `TradingStore` 接口
2. 修改 `get_db()` 依赖注入
3. 业务逻辑层无需改动

### 7.3 真实交易所接入

1. 替换 `MockExchange` 或扩展其实现
2. 接入币安/OKX 等真实 API
3. 保持接口不变，业务逻辑复用
