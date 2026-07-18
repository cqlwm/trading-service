# 跨服务集成设计

## 1. 集成总览

Trading Service 与 News Service 采用 **共享数据库 + 双向 HTTP API** 的集成模式。

```mermaid
graph LR
    subgraph "Trading Service (8001)"
        TS_API[FastAPI]
        TS_DB[(trading_* 表)]
    end
    
    subgraph "News Service (8000)"
        NS_API[FastAPI]
        NS_DB[(news_*, market_* 表)]
    end
    
    TS_API -->|拉取市场数据| NS_API
    NS_API -->|触发策略执行| TS_API
    
    TS_DB -.->|共享 SQLite 文件| NS_DB
```

### 1.1 集成方式对比

| 集成方式 | 适用场景 | 当前使用 |
|----------|----------|----------|
| **共享数据库** | 两服务紧密协作，数据强一致 | ✅ 使用 |
| **HTTP API** | 异步操作，跨服务调用 | ✅ 使用 |
| **消息队列** | 高吞吐解耦 | ❌ 暂不使用 |
| **gRPC** | 高性能内部调用 | ❌ 暂不使用 |

---

## 2. 共享数据库设计

### 2.1 数据库文件位置

```
~/projects/news-service/news.db
```

### 2.2 表命名空间约定

| 表前缀 | 归属服务 | 说明 |
|--------|----------|------|
| `news_*` | News Service | 新闻、爬取、原始数据 |
| `market_*` | News Service | 市场数据、K线、市值排名 |
| `trading_*` | Trading Service | 持仓、订单、信号 |

### 2.3 跨服务数据访问规则

**Trading Service 只读 News Service 表**：
- `market_klines` - K线数据
- `market_rankings` - 市值排名
- `news_articles` - 新闻文章

**Trading Service 自己管理 `trading_signals` 表**：
- 信号由 Trading Service 的信号检测器（`SignalDetector` 子类）产出并落盘
- 信号检测器与策略平行，由调度器定时调度
- 信号可被策略消费（驱动交易），也可不被消费（仅用于内容生成）
- 外部服务（如 News Service）如需传递信号，应通过 `POST /api/signals` API 调用，不直接写共享表

### 2.4 SQLite 并发注意事项

```mermaid
graph TD
    A[SQLite 并发特性] --> B[读可并行]
    A --> C[写串行化]
    C --> D[写操作会锁库]
    D --> E[避免长事务]
    D --> F[频繁写会影响读性能]
```

**最佳实践**：
- 控制事务大小，长操作分批执行
- 写操作尽量合并，减少锁竞争
- 考虑 WAL 模式提升并发读性能

---

## 3. Trading Service → News Service 调用

### 3.1 调用点汇总

| 调用方 | 接口 | 用途 | 频率 |
|--------|------|------|------|
| `MockExchange` | `GET /api/market/prices` | 获取最新价格、盈亏计算（占位实现，待接入） | 策略执行时 |
| `Strategy` | `GET /api/delistings` | 退市币种黑名单 | 每日一次 |

> **说明**：币种筛选（`AlphaTokenSource`）与技术分析（`TechnicalAnalysisFilter` + `ITechnicalAnalyzer`）当前通过 `BinanceClient` 直接调用币安 API 获取 Alpha 代币列表、合约交易所信息与 K 线数据，不经过 News Service。后续计划通过 News Service API 获取数据（当前为 stub）。

### 3.2 HTTP 客户端配置

**配置项**（`config.py`）：
| 配置 | 值 | 说明 |
|------|----|------|
| `news_service_base_url` | `http://127.0.0.1:8000` | News Service 地址 |
| `news_service_timeout` | `30` | 超时时间（秒） |

### 3.3 币种筛选数据流

选币管道（`SelectionPipeline`）直接调用币安 API（不经 News Service）：

```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant Pipeline as SelectionPipeline
    participant Source as AlphaTokenSource
    participant Filter as TechnicalAnalysisFilter
    participant Analyzer as ITechnicalAnalyzer
    participant Binance as BinanceClient

    Strategy->>Pipeline: pick()
    Pipeline->>Source: fetch()
    Source->>Binance: get_alpha_tokens() + get_future_exchange_info()
    Binance-->>Source: Alpha 代币 + 可交易合约
    Source->>Source: 取交集
    Source->>Binance: get_future_ticker_24hr()（批量取合约最新价）
    Binance-->>Source: 合约 24h ticker
    Source->>Source: circulating_supply × 合约价 = 市值，过滤 < 5000万
    Source-->>Pipeline: list[SymbolInfo]（基础字段）
    Pipeline->>BullishFilter: apply(infos)
    BullishFilter->>Binance: get_future_klines(symbol, "1d", 5)
    Binance-->>BullishFilter: 1d K 线
    Note over BullishFilter: 存入 klines["1d"]，丢弃非阳线
    BullishFilter-->>Pipeline: list[SymbolInfo]（含 klines["1d"]）
    Pipeline->>TechFilter: apply(infos)
    TechFilter->>Analyzer: detect_200sma_signal(df)
    Analyzer-->>TechFilter: CrossSignal | None
    Note over TechFilter: 纯增强：写入 klines["4h"]，不丢弃
    TechFilter-->>Pipeline: list[SymbolInfo]（含 klines["1d"] + klines["4h"]）
    Pipeline-->>Strategy: list[SymbolInfo]
```

### 3.4 容错设计

**重试机制**：
```python
# 建议实现：
# - 连接失败重试 3 次
# - 指数退避: 1s, 2s, 4s
# - 超时保护: 30s
```

**降级策略**：
- News Service 不可用时，使用缓存数据
- 策略执行标记为部分成功
- 写入错误日志，不阻塞主流程

---

## 4. News Service → Trading Service 调用

### 4.1 调用点汇总

| 调用方 | 接口 | 触发时机 | 说明 |
|--------|------|----------|------|
| Cron 调度器 | `POST /api/strategies/martingale/execute` | 每 1 小时 | 定时执行马丁策略 |
| Cron 调度器 | `POST /api/strategies/micro-cap/execute` | 每 24 小时 | 微市值策略调仓 |
| 信号检测器 | `POST /api/strategies/martingale/execute` | 重大新闻时 | 新闻触发策略 |
| 监控面板 | 各类查询 API | 实时 | 前端展示调用 |

### 4.2 定时触发流程

```mermaid
sequenceDiagram
    participant Cron as News Service Cron
    participant TS as Trading Service
    participant Strategy as Strategy Engine
    participant DB as 数据库

    Note over Cron: 每小时触发
    
    Cron->>TS: POST /api/strategies/martingale/execute
    TS->>Strategy: execute()
    
    Strategy->>DB: 查询当前持仓
    Strategy->>Strategy: 检查盈亏状态
    
    alt 需要加仓/平仓
        Strategy->>DB: 更新持仓 + 写入订单
        Strategy-->>TS: {actions: [...]}
    else 无操作
        Strategy-->>TS: {actions: []}
    end
    
    TS-->>Cron: 200 OK + 执行结果
```

### 4.3 信号触发流程

```mermaid
sequenceDiagram
    participant NS as News Service
    participant Detector as Signal Detector
    participant TS as Trading Service
    participant DB as 数据库

    NS->>Detector: 检测到重大新闻
    Detector->>Detector: 计算信号严重度
    
    alt severity >= 3
        Detector->>TS: POST /api/signals (写入信号记录)
        Detector->>TS: POST /api/strategies/martingale/execute
        TS->>DB: 更新持仓
        TS-->>Detector: 执行结果
    end
```

---

## 5. 接口契约

### 5.1 News Service API 契约

**GET /api/rankings**
```python
# 请求
GET /api/rankings?limit=200&min_volume=1000000

# 响应
[
    {
        "symbol": "BTC",
        "rank": 1,
        "market_cap": 800000000000,
        "volume_24h": 25000000000,
        "price_change_24h": 2.5,
        "is_delisted": false
    }
]
```

**GET /api/market/prices**
```python
# 请求
GET /api/market/prices?symbols=BTC,ETH,BNB

# 响应
{
    "BTC": 42000.5,
    "ETH": 2500.0,
    "BNB": 300.0
}
```

### 5.2 Trading Service API 契约

详见 [05-api-design.md](./05-api-design.md)

---

## 6. 集成测试

### 6.1 集成测试场景

| 场景 | 测试要点 |
|------|----------|
| **数据库共享** | 两服务同时读写不冲突 |
| **双向调用** | Trading 调 News，News 调 Trading |
| **故障转移** | 一方不可用时，另一方优雅降级 |
| **并发调用** | 多个策略同时执行，数据库一致性 |

### 6.2 测试工具

```python
# 使用 pytest + httpx.AsyncClient
@pytest.fixture
def news_service_mock(respx_mock):
    respx_mock.get("http://127.0.0.1:8000/api/rankings").mock(
        return_value=httpx.Response(200, json=[...])
    )
```

---

## 7. 部署配置

### 7.1 环境变量配置

Trading Service `.env`：
```bash
# Trading Service 自身配置
TRADING_HOST=0.0.0.0
TRADING_PORT=8001
TRADING_DEBUG=false

# 数据库配置（共享）
TRADING_DB_PATH=/path/to/news-service/news.db

# News Service 集成
TRADING_NEWS_SERVICE_BASE_URL=http://127.0.0.1:8000
TRADING_NEWS_SERVICE_TIMEOUT=30

# 交易所配置（未来真实接入）
TRADING_BINANCE_API_KEY=
TRADING_BINANCE_API_SECRET=
```

### 7.2 启动顺序

```
1. 确保 SQLite 数据库文件存在
2. 启动 News Service (端口 8000)
3. 启动 Trading Service (端口 8001)
```

---

## 8. Binance Square 发布集成

### 8.1 集成概述

Trading Service 在策略执行产生动作后，可选自动生成贴文并发布到 Binance Square，
由 `trading_service/content/publisher.py` 的 `BinancePublisher` 负责。
发布通过 `binance_service` 包驱动 Playwright 自动化操作 Binance Square 网页，
属于**外部系统自动化集成**（非 HTTP API）。

### 8.2 调用链

```mermaid
graph LR
    S[AsyncIOScheduler] -->|await| PG[PostGenerator.generate_for_execution]
    PG -->|asyncio.to_thread| TP[_try_publish 同步]
    TP -->|enqueue 入队即返回| Q[task_queue]
    Q --> W[专属 worker 线程]
    W --> BS[BinanceService: open/create_postx/close]
    BS --> PW[Playwright sync_api]
    PW --> BIN[Binance Square 网页]
    W -->|call_soon_threadsafe| LOOP[asyncio 事件循环]
    LOOP --> CB[on_success/on_failure async 回调]
    CB -->|update_post_publish_result| DB[PostRecord 回写]

    API[api/posts.py 手动发布] -->|enqueue 入队即返回 202| Q
```

两个调用点共用同一个 `BinancePublisher` 单例（注入自 `api/deps.py`），
均通过 `enqueue` 入队后立即返回：
- `PostGenerator._try_publish`：策略定时执行后的自动发布（在 `to_thread` worker 内调 enqueue）
- `api/posts.py` 手动发布端点：返回 202 pending，结果异步回写

### 8.3 并发模型：专属 worker 线程 + 异步回调管道（关键设计）

**背景问题**：Playwright sync API 是**线程绑定**的--浏览器对象绑死在
`open()` 时的 greenlet/线程上，之后所有操作必须在同一线程发起，否则抛
`Cannot switch to a different thread`。且 `create_postx` 耗时几十秒，
若调用方同步阻塞等待，会长时间占用调用线程。

**解决方案**：`BinancePublisher` 内部起**一条专属 worker 线程**串行消费队列，
Playwright 操作（`open / create_postx / close`）全部在该线程执行。
`enqueue` 入队后**立即返回**，不阻塞调用方；worker 完成后通过
`loop.call_soon_threadsafe(asyncio.create_task, callback)` 把 async 回调
调度回 asyncio 事件循环线程执行。

| 特性 | 说明 |
|------|------|
| 入队即返回 | `enqueue` 投任务后立即返回，调用方不等 Playwright（几十秒） |
| 线程亲和 | Playwright 操作固定在专属 worker 线程，规避跨线程限制 |
| 串行消费 | worker 单线程串行取队列任务，`create_postx` 不重叠 |
| 异步回调 | 成功 `on_success(publish_id, share_link)` / 失败 `on_failure(publish_id, error)`，async，在事件循环线程执行 |
| loop 注入 | `set_loop` 在 FastAPI lifespan（loop 线程）注入事件循环，供 worker 跨线程调度回调 |
| 即用即弃（队列空触发） | 一批密集到达的任务复用同一浏览器实例；**队列排空**（无待发任务）时才关闭 `BinanceService` 释放 Chrome 进程，下一批任务到达时重新打开。避免批量入队时反复开关浏览器 |
| 失败不重试 | 只调 `on_failure`，是否重试由调用方决定 |
| 回写职责 | PostRecord 的 `published_at/share_link/publish_error` 由全局回调回写（deps.py 注入），PostGenerator 不再直接回写 |

### 8.4 容错设计

- **发布失败不影响策略执行**：`scheduler._execute_strategy` 中贴文生成/发布
  包在 `try/except` 内，异常仅记录日志（见 `scheduler.py:226-230`）。
- **异常路径不泄漏浏览器**：`_process_task` 异常由 `try/except` 捕获并转 `on_failure`，
  不影响 worker 继续消费；浏览器在队列排空时由 `_drain_queue` 统一释放，
  即使最后一个任务异常也会触发释放。
- **异常后 worker 可恢复**：一次 `create_postx` 异常不会终止 worker 线程，
  继续消费后续队列任务。
- **loop 未注入降级**：`enqueue` 时若 `set_loop` 未调用，记录 warning，
  create_postx 仍执行但回调被丢弃（正常启动流程 lifespan 先于调度，不会触发）。
- **close 幂等**：多次调用 `close()` 不崩溃；投哨兵让 worker 退出。

### 8.5 调用点契约变更

| 调用点 | 旧契约 | 新契约 |
|------|--------|--------|
| `PostGenerator._try_publish` | 同步调 `publish_postx`，成功/失败直接回写 PostRecord | 调 `enqueue` 入队即返回，回写由 publisher 回调异步完成 |
| `POST /api/posts/{id}/publish` | 同步阻塞，返回 `{status, post_id, share_link}` | 入队即返回 **202** `{status:"pending", post_id, publish_id}`，前端轮询 GET 贴文详情取 `share_link/publish_error` |

### 8.6 测试策略

- `test_publisher_async.py`：异步管道核心测试，用真实 asyncio loop +
  `service_factory` 注入。验证 enqueue 立即返回（<0.1s）、worker 串行消费、
  `on_success`/`on_failure` 在事件循环线程触发（非 worker 线程）、
  浏览器每次释放（open/close 次数 == 发布次数）、loop 未注入降级。
- `test_publisher.py`：不依赖管道的纯函数（`resolve_base_asset`）与配置加载。
- `test_post_generator_publish.py`：`FakePublisher` 实现 `enqueue`/`set_loop`/
  `close`，enqueue 时同步模拟回写，验证 PostGenerator 正确入队 + 回写闭环。

---

## 9. 未来演进方向

### 9.1 短期优化

- [ ] 实现 HTTP 客户端重试机制
- [ ] SQLite WAL 模式开启
- [ ] 调用认证（API Key）
- [ ] 请求日志与链路追踪

### 9.2 中期演进

```mermaid
graph LR
    A[当前: 共享 DB] --> B[独立 DB + API]
    B --> C[消息队列解耦]
    C --> D[微服务完整架构]
```

### 9.3 长期目标

| 方向 | 方案 |
|------|------|
| **数据层** | PostgreSQL 替代 SQLite |
| **通信层** | Redis Pub/Sub 或 RabbitMQ |
| **服务发现** | 简单 Nginx 或 Consul |
| **可观测** | Prometheus + Grafana |
