# 数据流程图

## 1. 核心业务流程

### 1.1 策略执行流程

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as Strategy API
    participant Strategy as 策略引擎
    participant Picker as SymbolPicker
    participant Exchange as MockExchange
    participant NS as News Service
    participant DB as 数据库

    Client->>API: POST /api/strategies/{name}/execute
    API->>Strategy: execute()
    
    Strategy->>Picker: pick_symbols()
    Picker->>NS: GET /api/rankings (币种筛选)
    NS-->>Picker: 返回候选币种列表
    Picker-->>Strategy: 选中币种
    
    Strategy->>Exchange: 检查当前持仓
    Exchange->>DB: 查询 trading_positions
    DB-->>Exchange: 持仓数据
    Exchange-->>Strategy: 持仓状态
    
    alt 需要开仓
        Strategy->>Exchange: 创建新持仓
        Exchange->>DB: INSERT trading_positions
        Exchange->>DB: INSERT trading_orders (OPEN)
        Strategy-->>API: 开仓成功
    else 需要加仓
        Strategy->>Exchange: 加仓现有持仓
        Exchange->>DB: UPDATE trading_positions (total_size)
        Exchange->>DB: INSERT trading_orders (ADD)
        Strategy-->>API: 加仓成功
    else 需要平仓
        Strategy->>Exchange: close_position()
        Exchange->>DB: UPDATE trading_positions (status=closed)
        Exchange->>DB: INSERT trading_orders (CLOSE)
        Strategy-->>API: 平仓成功
    end
    
    API-->>Client: 执行结果
```

### 1.2 手动平仓流程

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as Positions API
    participant Exchange as MockExchange
    participant DB as 数据库

    Client->>API: POST /api/positions/{id}/close
    API->>Exchange: close_position(position_id, reason="manual")
    
    Exchange->>DB: SELECT trading_positions WHERE id = ?
    DB-->>Exchange: 持仓记录
    
    alt 持仓存在且 open
        Exchange->>Exchange: 计算盈亏 pnl_pct()
        Exchange->>DB: UPDATE status=closed, exit_price, closed_at
        Exchange->>DB: INSERT trading_orders (type=CLOSE)
        Exchange-->>API: CloseResult
        API-->>Client: 200 OK + 平仓结果
    else 持仓不存在或已关闭
        Exchange-->>API: None
        API-->>Client: 404 Not Found
    end
```

---

## 2. 数据查询流程

### 2.1 持仓详情查询

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as Positions API
    participant Exchange as MockExchange
    participant DB as 数据库

    Client->>API: GET /api/positions/{id}
    API->>Exchange: get_position_context(position_id)
    
    Exchange->>DB: SELECT * FROM trading_positions WHERE id = ?
    DB-->>Exchange: PositionRecord
    
    alt 持仓存在
        Exchange->>DB: SELECT * FROM trading_orders WHERE position_id = ?
        DB-->>Exchange: [OrderRecord...]
        
        Exchange->>Exchange: 构建 PositionContext
        Note right of Exchange: 包含 layers 计算<br/>订单列表整理<br/>时间格式化
        Exchange-->>API: PositionContext dict
        API-->>Client: 200 OK + 详情
    else 持仓不存在
        Exchange-->>API: None
        API-->>Client: 404 Not Found
    end
```

### 2.2 交易时间线查询

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as Timeline API
    participant Exchange as MockExchange
    participant DB as 数据库

    Client->>API: GET /api/timeline?limit=50
    API->>Exchange: get_timeline(limit=50)
    
    Exchange->>DB: SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT 50
    DB-->>Exchange: [SignalRecord...]
    
    Exchange->>DB: SELECT * FROM trading_orders ORDER BY created_at DESC LIMIT 50
    DB-->>Exchange: [OrderRecord...]
    
    Exchange->>Exchange: 合并两类事件
    Exchange->>Exchange: 按时间倒序排序
    Exchange->>Exchange: 截取 limit 条
    
    Exchange-->>API: [StoryEvent...]
    API-->>Client: 200 OK + 时间线列表
```

### 2.3 交易故事查询 (单 Symbol)

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as Timeline API
    participant Exchange as MockExchange
    participant DB as 数据库

    Client->>API: GET /api/story/BTC
    API->>Exchange: get_trade_story(symbol="BTC")
    
    Exchange->>DB: SELECT signals WHERE symbol = 'BTC' LIMIT 100
    DB-->>Exchange: [SignalRecord...]
    
    Exchange->>DB: SELECT orders WHERE symbol = 'BTC' LIMIT 100
    DB-->>Exchange: [OrderRecord...]
    
    Exchange->>Exchange: 合并信号与订单
    Exchange->>Exchange: 按时间正序排序 (事件发展顺序)
    
    Exchange-->>API: [StoryEvent...]
    API-->>Client: 200 OK + 交易故事
```

---

## 3. 跨服务数据流

### 3.1 Trading Service → News Service (市场数据)

```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant Exchange as MockExchange
    participant NS as News Service API

    Strategy->>Exchange: fetch_prices(symbols)
    Exchange->>NS: GET /api/market/prices?symbols=BTC,ETH...
    NS-->>Exchange: {symbol: price} dict
    Exchange-->>Strategy: 价格数据
```

**其他调用点：**
- 币种排名筛选：`GET /api/rankings`
- K线数据获取：`GET /api/klines/{symbol}`
- 退市币种检查：`GET /api/delistings`

### 3.2 News Service → Trading Service (策略触发)

```mermaid
sequenceDiagram
    participant NS as News Service
    participant TS as Trading Service
    participant Strategy as Strategy Engine

    NS->>TS: POST /api/strategies/martingale/execute
    TS->>Strategy: execute()
    
    alt 执行成功
        Strategy-->>TS: {"status": "success", "actions": [...]}
        TS-->>NS: 200 OK
    else 执行失败
        Strategy-->>TS: {"status": "error", "message": "..."}
        TS-->>NS: 500 Error
    end
```

---

## 4. 数据生命周期

### 4.1 持仓生命周期

```mermaid
stateDiagram-v2
    [*] --> open: 创建持仓 (OPEN 订单)
    open --> open: 加仓 (ADD 订单)
    open --> open: 部分减仓 (REDUCE 订单)
    open --> open: 止盈触发 (tp_hit++)
    open --> closed: 平仓 (CLOSE 订单)
    closed --> [*]
```

**状态说明：**

| 状态 | 说明 | 可执行操作 |
|------|------|------------|
| `open` | 持仓中 | 加仓、减仓、平仓 |
| `closed` | 已平仓 | 查询历史 |

### 4.2 订单类型流转

```mermaid
graph LR
    OPEN[OPEN<br/>开仓] --> ADD[ADD<br/>加仓]
    ADD --> REDUCE[REDUCE<br/>减仓]
    REDUCE --> CLOSE[CLOSE<br/>平仓]
    OPEN --> CLOSE
    ADD --> CLOSE
```

---

## 5. 数据流汇总图

```mermaid
flowchart TB
    subgraph "输入数据"
        S1[交易信号 Signal]
        S2[市场价格 Price]
        S3[币种排名 Rankings]
        S4[人工指令 Manual]
    end

    subgraph "核心处理"
        P1[策略执行<br/>Strategy.execute()]
        P2[持仓管理<br/>Position lifecycle]
        P3[订单生成<br/>Order creation]
    end

    subgraph "数据存储"
        D1[(trading_signals)]
        D2[(trading_positions)]
        D3[(trading_orders)]
    end

    subgraph "输出数据"
        O1[持仓详情 API]
        O2[订单列表 API]
        O3[时间线 Timeline]
        O4[交易故事 Story]
        O5[策略状态 Status]
    end

    S1 --> D1
    S2 --> P1
    S3 --> P1
    S4 --> P2

    P1 --> P2
    P2 --> P3
    
    P2 --> D2
    P3 --> D3

    D2 --> O1
    D3 --> O2
    D1 --> O3
    D2 --> O3
    D3 --> O3
    D1 --> O4
    D2 --> O4
    D3 --> O4
    P1 --> O5
```
