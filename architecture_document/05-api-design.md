# API 设计规范

## 1. REST API 设计原则

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| **资源导向** | URL 使用名词，避免动词 |
| **层级清晰** | `/api/{resource}/{id}/{action}` |
| **HTTP 方法语义** | GET=查询, POST=创建/执行, PUT=更新, DELETE=删除 |
| **统一响应格式** | 成功/错误使用固定结构 |
| **分页支持** | 列表接口支持 `limit` + `offset` |
| **过滤支持** | 列表接口支持查询参数过滤 |

### 1.2 URL 命名规范

```
GET    /api/{resource}          # 列表
GET    /api/{resource}/{id}     # 单个
POST   /api/{resource}/{id}/{action}  # 动作
```

**示例**：
```
GET    /api/positions           # 持仓列表
GET    /api/positions/a1b2c3    # 持仓详情
POST   /api/positions/a1b2c3/close  # 平仓动作
```

---

## 2. 全局 API 端点

### 2.1 服务信息与健康检查

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/` | 服务信息 | 无 |
| `GET` | `/health` | 健康检查 | 无 |

**响应示例 - GET /**:
```json
{
    "service": "trading-service",
    "version": "0.1.0",
    "status": "ok"
}
```

---

## 3. Positions API (持仓管理)

### 3.1 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/positions` | 持仓列表 |
| `GET` | `/api/positions/{id}` | 持仓详情 |
| `POST` | `/api/positions/{id}/close` | 手动平仓 |

### 3.2 GET /api/positions

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 按状态过滤: `open` / `closed` |
| `tag` | string | 否 | 按策略标签过滤 |
| `symbol` | string | 否 | 按币种过滤 |
| `limit` | int | 否 | 分页大小，默认 50 |
| `offset` | int | 否 | 偏移量，默认 0 |

**响应示例**:
```json
{
    "data": [
        {
            "id": "a1b2c3d4e5f6",
            "symbol": "BTCUSDT",
            "direction": "long",
            "entry_price": 42000.5,
            "total_size": 0.0015,
            "status": "open",
            "tag": "martingale",
            "tp_hit": 1,
            "layers": 2,
            "created_at": "2024-01-15T10:30:00Z",
            "closed_at": null
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
}
```

### 3.3 GET /api/positions/{id}

**成功响应 (200)**:
```json
{
    "id": "a1b2c3d4e5f6",
    "symbol": "BTCUSDT",
    "direction": "long",
    "entry_price": 42000.5,
    "total_size": 0.0015,
    "status": "open",
    "exit_price": null,
    "tag": "martingale",
    "tp_hit": 1,
    "layers": 2,
    "created_at": "2024-01-15T10:30:00Z",
    "closed_at": null,
    "orders": [
        {
            "id": "x1y2z3",
            "order_type": "OPEN",
            "size": 0.001,
            "price": 41000.0,
            "direction": "long",
            "created_at": "2024-01-15T10:30:00Z"
        },
        {
            "id": "k4j5h6",
            "order_type": "ADD",
            "size": 0.0005,
            "price": 40000.0,
            "direction": "long",
            "created_at": "2024-01-15T11:00:00Z"
        }
    ]
}
```

**错误响应 (404)**:
```json
{
    "detail": "Position not found"
}
```

### 3.4 POST /api/positions/{id}/close

**请求体**: 无（手动平仓使用默认 reason_text="手动平仓"）

**成功响应 (200)**:
```json
{
    "position_id": "a1b2c3d4e5f6",
    "close_price": 42000.5,
    "pnl_pct": 0.0
}
```

---

## 4. Orders API (订单查询)

### 4.1 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/orders` | 订单列表（支持过滤） |

### 4.2 GET /api/orders

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 否 | 币种过滤 |
| `position_id` | string | 否 | 按持仓过滤 |
| `order_type` | string | 否 | 类型: OPEN/ADD/REDUCE/CLOSE |
| `limit` | int | 否 | 默认 50 |
| `offset` | int | 否 | 默认 0 |

**响应示例**:
```json
{
    "data": [
        {
            "id": "x1y2z3",
            "position_id": "a1b2c3d4e5f6",
            "symbol": "BTCUSDT",
            "direction": "long",
            "size": 0.001,
            "price": 41000.0,
            "order_type": "OPEN",
            "created_at": "2024-01-15T10:30:00Z"
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
}
```

---

## 5. Signals API (信号查询)

### 5.1 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/signals` | 信号列表（支持严重度过滤） |

### 5.2 GET /api/signals

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | string | 否 | 币种过滤 |
| `signal_type` | string | 否 | 信号类型过滤 |
| `min_severity` | int | 否 | 最小严重度 (0-5) |
| `limit` | int | 否 | 默认 50 |
| `offset` | int | 否 | 默认 0 |

**响应示例**:
```json
{
    "data": [
        {
            "id": "s1g2n3",
            "symbol": "BTC",
            "signal_type": "news_surge",
            "direction": "bullish",
            "severity": 4,
            "description": "比特币 ETF 通过",
            "metadata": {"source": "twitter"},
            "created_at": "2024-01-15T10:30:00Z"
        }
    ],
    "total": 1,
    "limit": 50,
    "offset": 0
}
```

---

## 6. Timeline API (时间线与交易故事)

### 6.1 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/timeline` | 全局交易时间线 |
| `GET` | `/api/story/{symbol}` | 单币种交易故事 |

### 6.2 GET /api/timeline

**查询参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | int | 否 | 默认 50 |
| `offset` | int | 否 | 默认 0 |

**响应示例**:
```json
{
    "data": [
        {
            "timestamp": "2024-01-15T11:00:00Z",
            "event_type": "order",
            "data": {
                "id": "k4j5h6",
                "order_type": "ADD",
                "symbol": "BTCUSDT",
                "size": 0.0005,
                "price": 40000.0
            }
        },
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "event_type": "signal",
            "data": {
                "id": "s1g2n3",
                "symbol": "BTC",
                "signal_type": "news_surge",
                "severity": 4
            }
        }
    ],
    "limit": 50,
    "offset": 0
}
```

### 6.3 GET /api/story/{symbol}

**说明**：返回指定币种的完整交易故事，按时间正序排列。

**响应示例**:
```json
{
    "symbol": "BTC",
    "events": [
        {
            "timestamp": "2024-01-15T10:00:00Z",
            "event_type": "signal",
            "data": {...}
        },
        {
            "timestamp": "2024-01-15T10:30:00Z",
            "event_type": "order",
            "data": {...}
        }
    ]
}
```

---

## 7. Strategies API (策略执行)

### 7.1 端点汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/strategies/martingale/execute` | 执行马丁策略 |
| `GET` | `/api/strategies/martingale/status` | 马丁策略状态 |
| `POST` | `/api/strategies/micro-cap/execute` | 执行微市值策略 |
| `GET` | `/api/strategies/micro-cap/status` | 微市值策略状态 |
| `GET` | `/api/strategies/micro-cap/history` | 微市值历史记录 |

### 7.2 POST /api/strategies/{name}/execute

**请求体 (可选)**：
```json
{
    "dry_run": false,    // 试运行，不实际执行
    "symbol": "BTC"      // 指定单币种执行
}
```

**成功响应 (200)**:
```json
{
    "status": "success",
    "strategy": "martingale",
    "actions": [
        {
            "type": "add_layer",
            "symbol": "BTCUSDT",
            "position_id": "a1b2c3d4e5f6",
            "size": 0.0005,
            "price": 40000.0
        },
        {
            "type": "take_profit",
            "symbol": "ETHUSDT",
            "position_id": "b2c3d4e5f6g7",
            "pnl_pct": 1.2
        }
    ],
    "timestamp": "2024-01-15T12:00:00Z"
}
```

### 7.3 GET /api/strategies/{name}/status

**响应示例 (martingale)**:
```json
{
    "strategy": "martingale",
    "config": {
        "max_layers": 5,
        "base_size": 0.001,
        "multiplier": 2.0,
        "tp_pct": 1.0
    },
    "active_positions": 3,
    "total_layers": 7,
    "statistics": {
        "total_trades": 42,
        "win_rate": 0.72,
        "avg_profit_pct": 1.2
    },
    "last_execution": {
        "timestamp": "2024-01-15T12:00:00Z",
        "actions_performed": ["add_layer", "take_profit"]
    }
}
```

---

## 8. 错误响应规范

### 8.1 HTTP 状态码

| 状态码 | 场景 |
|--------|------|
| `200` | 成功 |
| `400` | 请求参数错误 |
| `404` | 资源不存在 |
| `422` | 请求体验证失败 (Pydantic) |
| `500` | 服务器内部错误 |

### 8.2 统一错误格式

```json
{
    "detail": [
        {
            "type": "value_error",
            "loc": ["body", "symbol"],
            "msg": "Invalid symbol format",
            "input": "INVALID"
        }
    ]
}
```

---

## 9. API 文档访问

### 9.1 Swagger UI (交互式文档)

```
http://127.0.0.1:8001/docs
```

**功能**：
- 在线 API 调试
- 请求/响应示例
- Schema 定义
- "Try it out" 执行真实请求

### 9.2 ReDoc (阅读文档)

```
http://127.0.0.1:8001/redoc
```

**功能**：
- 结构化文档展示
- 适合打印/分享
- 完整 Schema 导航

---

## 10. CORS 配置

**当前配置**（开发环境）：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 允许所有源
    allow_credentials=True,
    allow_methods=["*"],      # 允许所有方法
    allow_headers=["*"],      # 允许所有头
)
```

**生产环境建议**：
- 明确指定 `allow_origins` 白名单
- 限制 `allow_methods` 为实际使用的 HTTP 方法
