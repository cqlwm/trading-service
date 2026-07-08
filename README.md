# Trading Service

独立交易服务，包含策略引擎、仓位管理、订单执行。

## 架构

```
Trading Service (端口 8001)
├── FastAPI API 层
│   ├── /api/positions    - 持仓管理
│   ├── /api/orders       - 订单查询
│   ├── /api/signals      - 信号查询
│   ├── /api/timeline     - 时间线
│   ├── /api/story/{symbol} - 交易故事
│   └── /api/strategies   - 策略执行
├── 业务逻辑层
│   ├── MockExchange      - 交易所模拟
│   └── TradingStore      - 数据存储（SQLAlchemy ORM）
├── 数据模型
│   └── models.py         - SQLAlchemy 模型定义
├── 迁移系统
│   └── Alembic           - 数据库 Schema 版本管理
└── 策略引擎
    ├── MartingaleStrategy - 马丁格尔策略
    └── MicroCapStrategy  - 微市值策略
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd /Users/li/projects/trading-service
uv venv
source .venv/bin/activate
uv sync
```

### 2. 配置文件

复制 `config.yaml` 为 `config.local.yaml` 并修改本地配置：

```bash
cp config.yaml config.local.yaml
# 编辑 config.local.yaml，修改数据库路径等配置
```

### 3. 启动服务

```bash
python main.py
# 或
uvicorn trading_service.app:app --host 0.0.0.0 --port 8001 --reload
```

**启动时自动行为**：
- 检查数据库 Schema 版本
- 自动执行未完成的 Alembic 迁移
- 如果数据库不存在，自动创建并初始化表结构

### 4. 访问 API 文档

- Swagger UI: http://127.0.0.1:8001/docs
- ReDoc: http://127.0.0.1:8001/redoc

## 数据库 Schema 管理

项目使用 **SQLAlchemy 2.0 + Alembic** 进行 ORM 和 Schema 版本管理。

### 修改 Schema 流程

1. **编辑模型**：修改 `trading_service/models.py` 中的数据模型
2. **生成迁移**：运行以下命令自动检测变更并生成迁移脚本：
   ```bash
   alembic revision --autogenerate -m "描述你的变更"
   ```
3. **检查迁移**：检查生成的迁移脚本 `migrations/versions/xxx.py`
4. **执行迁移**：重启服务会自动执行，或手动执行：
   ```bash
   alembic upgrade head
   ```

### 常用 Alembic 命令

```bash
# 生成迁移脚本（自动检测模型变更）
alembic revision --autogenerate -m "描述"

# 执行迁移到最新版本
alembic upgrade head

# 回退一个版本
alembic downgrade -1

# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/api/positions` | 持仓列表 |
| GET | `/api/positions/{id}` | 持仓详情 |
| POST | `/api/positions/{id}/close` | 手动平仓 |
| GET | `/api/orders` | 订单列表 |
| GET | `/api/signals` | 信号列表 |
| GET | `/api/timeline` | 全局时间线 |
| GET | `/api/story/{symbol}` | 交易故事 |
| POST | `/api/strategies/martingale/execute` | 执行马丁策略 |
| GET | `/api/strategies/martingale/status` | 马丁策略状态 |
| POST | `/api/strategies/micro-cap/execute` | 执行微市值策略 |
| GET | `/api/strategies/micro-cap/status` | 微市值策略状态 |
| GET | `/api/strategies/micro-cap/history` | 微市值历史记录 |

## 与 News Service 集成

Trading Service 通过 HTTP API 与 News Service 交互：

1. Trading Service 调用 News Service 获取：
   - 市场数据（K线、价格）
   - 币种排名和筛选
   - 退市币种信息

2. News Service 调用 Trading Service 触发：
   - 策略执行（定时任务）
   - 基于新闻信号的交易触发

## 数据库

Trading Service 与 News Service 共享 SQLite 数据库，各自操作不同的表：

- `trading_positions` - 持仓表
- `trading_orders` - 订单表
- `trading_signals` - 信号表

**注意**：表结构完全由 `trading_service/models.py` 定义，通过 Alembic 迁移管理。禁止手工修改表结构。

## 目录结构

```
trading_service/
├── __init__.py
├── app.py              # FastAPI 入口
├── config.py           # 配置管理（YAML + 环境变量）
├── types.py            # 枚举类型定义
├── exchange.py         # MockExchange - 业务核心
├── store.py            # 数据访问层（SQLAlchemy ORM）
├── models.py           # SQLAlchemy 数据模型定义
├── migration_check.py  # 启动时迁移校验
│
├── api/                # API 层
│   ├── deps.py         - 依赖注入（禁止业务逻辑！）
│   ├── positions.py
│   ├── orders.py
│   ├── signals.py
│   ├── timeline.py
│   └── strategies.py
│
├── strategies/         # 策略引擎层
│   ├── base.py         # Strategy 抽象基类
│   ├── martingale.py
│   ├── micro_cap.py
│   └── symbol_picker.py
│
└── utils/              # 纯工具函数（无状态）
    └── symbol.py

migrations/             # Alembic 迁移脚本
├── versions/           # 版本化迁移脚本
└── env.py              #  Alembic 环境配置
```
