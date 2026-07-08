# Trading Service 架构文档

## 文档索引

| 文档 | 说明 |
|------|------|
| [01-system-architecture.md](./01-system-architecture.md) | 系统整体架构、分层设计、技术栈 |
| [02-data-flow.md](./02-data-flow.md) | 业务数据流、核心功能流程图 |
| [03-domain-model.md](./03-domain-model.md) | 领域模型、数据库表结构设计 |
| [04-strategy-engine.md](./04-strategy-engine.md) | 策略引擎架构、策略实现机制 |
| [05-api-design.md](./05-api-design.md) | REST API 设计规范、端点说明 |
| [06-integration.md](./06-integration.md) | 跨服务集成、News Service 交互 |

## 快速导航

```
architecture_document/
├── README.md                    # 本文档
├── 01-system-architecture.md    # 系统架构总览
├── 02-data-flow.md              # 数据流程
├── 03-domain-model.md           # 领域模型
├── 04-strategy-engine.md        # 策略引擎
├── 05-api-design.md             # API 设计
├── 06-integration.md            # 服务集成
└── diagrams/                    # 图表资源目录
```

## 项目概述

Trading Service 是一个独立的加密货币交易服务，负责：
- 策略执行引擎（马丁格尔、微市值策略）
- 持仓生命周期管理
- 订单追踪与查询
- 交易信号存储
- 交易时间线与故事生成

**服务端口**：8001  
**数据库**：SQLite (与 News Service 共享)  
**技术栈**：Python + FastAPI + uv
