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
│   └── TradingStore      - 数据存储
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

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

### 3. 启动服务

```bash
python main.py
# 或
uvicorn trading_service.app:app --host 0.0.0.0 --port 8001 --reload
```

### 4. 访问 API 文档

- Swagger UI: http://127.0.0.1:8001/docs
- ReDoc: http://127.0.0.1:8001/redoc

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
