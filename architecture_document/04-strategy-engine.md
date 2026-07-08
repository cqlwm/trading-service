# 策略引擎设计

## 1. 策略引擎架构

### 1.1 核心类层次结构

```mermaid
classDiagram
    class Strategy {
        <<abstract>>
        +exchange: MockExchange
        +config: StrategyConfig
        +symbol_picker: ISymbolPicker
        +execute()*
        +get_status()*
    }

    class StrategyConfig {
        <<dataclass>>
        策略配置基类
    }

    class ISymbolPicker {
        <<interface>>
        +pick_symbols() list[str]
    }

    class MartingaleStrategy {
        +execute()
        +get_status()
    }

    class MartingaleConfig {
        +max_layers: int
        +base_size: float
        +multiplier: float
        +tp_pct: float
    }

    class MicroCapStrategy {
        +execute()
        +get_status()
        +get_history()
    }

    class MicroCapConfig {
        +portfolio_size: int
        +rebalance_hours: int
        +min_volume: float
    }

    class NewsServiceSymbolPicker {
        +pick_symbols() list[str]
    }

    Strategy --> StrategyConfig
    Strategy --> ISymbolPicker
    
    Strategy <|-- MartingaleStrategy
    Strategy <|-- MicroCapStrategy
    
    StrategyConfig <|-- MartingaleConfig
    StrategyConfig <|-- MicroCapConfig
    
    ISymbolPicker <|-- NewsServiceSymbolPicker
```

---

## 2. 策略基类设计

### 2.1 Strategy 抽象基类

**文件**：`trading_service/strategies/base.py`

```python
@dataclass
class StrategyConfig:
    """策略配置基类"""

class Strategy(ABC):
    def __init__(
        self,
        exchange: MockExchange,
        config: StrategyConfig,
        symbol_picker: ISymbolPicker,
    ) -> None:
        self.exchange = exchange
        self.config = config
        self.symbol_picker = symbol_picker

    @abstractmethod
    async def execute(self) -> None:
        """执行策略 - 核心逻辑入口"""

    @abstractmethod
    def get_status(self) -> dict:
        """获取策略当前状态 - 用于 API 响应"""
```

**设计原则**：
1. **依赖注入**：所有外部依赖通过构造函数注入
2. **单一职责**：Strategy 只负责策略逻辑，不处理数据存储
3. **异步执行**：`execute()` 是 async 方法，支持耗时操作
4. **状态暴露**：`get_status()` 提供人类可读的状态信息

---

## 3. 币种选择器

### 3.1 ISymbolPicker 接口

```python
class ISymbolPicker(ABC):
    @abstractmethod
    async def pick_symbols(self, count: int) -> list[str]:
        """选择符合策略条件的币种"""
```

### 3.2 实现说明

当前实现通过 **News Service API** 获取：
- 币种市值排名
- 24h 成交量筛选
- 涨跌幅过滤
- 退市币种排除

**调用流程**：
```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant Picker as SymbolPicker
    participant NS as News Service

    Strategy->>Picker: pick_symbols(count=10)
    Picker->>NS: GET /api/rankings?limit=50&min_volume=1000000
    NS-->>Picker: 币种列表 (带市值、成交量、涨跌幅)
    Picker->>Picker: 过滤微市值、排除退市
    Picker-->>Strategy: [symbol...]
```

---

## 4. 马丁格尔策略 (Martingale)

### 4.1 策略原理

```mermaid
graph TD
    A[检查当前持仓] --> B{有亏损持仓?}
    
    B -->|是| C[亏损 > 加仓阈值?]
    C -->|是| D[加倍加仓<br/>size = base * multiplier^layer]
    C -->|否| E[等待]
    
    B -->|否| F[有无止盈触发?]
    F -->|是| G[重置层数<br/>tp_hit++]
    F -->|否| H[开新仓]
    
    D --> I[检查层数 < max_layers]
    I -->|是| J[执行加仓]
    I -->|否| K[强制平仓止损]
```

### 4.2 配置参数 (MartingaleConfig)

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_layers` | int | 5 | 最大加仓层数 |
| `base_size` | float | 0.001 | 初始仓位大小 |
| `multiplier` | float | 2.0 | 加仓倍率 (马丁核心) |
| `tp_pct` | float | 1.0 | 止盈百分比 |
| `add_threshold_pct` | float | -2.0 | 加仓触发阈值 (亏损) |

### 4.3 仓位大小计算公式

```
第 0 层 (初始): size = base_size
第 1 层: size = base_size * multiplier
第 2 层: size = base_size * multiplier^2
...
第 N 层: size = base_size * multiplier^N
```

**累计持仓**:
```
total_size = base_size * (multiplier^(n+1) - 1) / (multiplier - 1)
```

**盈亏平衡点 (做多为例)**:
```
breakeven_price = Σ(price_i * size_i) / total_size
```

---

## 5. 微市值策略 (MicroCap)

### 5.1 策略原理

```mermaid
graph TD
    A[获取微市值币种列表] --> B[筛选 Top N 币种]
    B --> C[检查持仓币种]
    
    C --> D{币种仍在 Top N?}
    D -->|是| E[继续持有]
    D -->|否| F[卖出换仓]
    
    C --> G{新币种进入 Top N?}
    G -->|是| H[买入新币种]
    G -->|否| I[不操作]
    
    F --> J[调仓完成]
    H --> J
```

### 5.2 配置参数 (MicroCapConfig)

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `portfolio_size` | int | 10 | 持仓币种数量 |
| `rebalance_hours` | int | 24 | 调仓间隔 (小时) |
| `min_volume_24h` | float | 1,000,000 | 最低 24h 成交量 ($) |
| `max_market_cap_rank` | int | 200 | 最大市值排名 |
| `equal_weight` | bool | True | 是否等权重分配 |

### 5.3 调仓逻辑

1. **获取候选池**：市值 100-200 名，成交量 > $1M
2. **评分排序**：结合波动率、成交量、社交热度
3. **组合构建**：等权重分配资金到 Top N 币种
4. **调仓执行**：
   - 移出不在 Top N 的币种
   - 买入新进入 Top N 的币种
   - 调整仓位至目标权重

---

## 6. 策略执行流程

### 6.1 通用执行流程

```mermaid
flowchart TB
    Start([策略触发]) --> Init[初始化依赖]
    Init --> Pick[选择币种 SymbolPicker]
    Pick --> Check[检查现有持仓 MockExchange]
    
    Check --> Logic[策略核心逻辑]
    Logic --> Actions{产生交易动作?}
    
    Actions -->|是| Open[开仓]
    Actions -->|是| Add[加仓]
    Actions -->|是| Close[平仓]
    Actions -->|否| Noop[无操作]
    
    Open --> Save[写入数据库]
    Add --> Save
    Close --> Save
    
    Save --> Result[返回执行结果]
    Noop --> Result
    Result --> End([结束])
```

### 6.2 策略触发方式

| 触发方式 | 说明 | 实现 |
|----------|------|------|
| **API 触发** | 显式调用策略接口 | `POST /api/strategies/{name}/execute` |
| **定时任务** | News Service Cron 定时调用 | 由 News Service 调度 |
| **信号触发** | 基于 News Service 事件触发 | Webhook / 轮询 |

---

## 7. 策略状态报告

每个策略必须实现 `get_status()` 方法，返回结构化状态信息。

### 7.1 状态格式规范

```python
{
    "strategy": "martingale",           # 策略名称
    "config": { ... },                  # 当前配置摘要
    "active_positions": 3,              # 活跃持仓数
    "total_layers": 7,                  # 总加仓层数
    "statistics": {                     # 统计数据
        "total_trades": 42,
        "win_rate": 0.72,
        "avg_profit_pct": 1.2,
    },
    "last_execution": {                 # 上次执行情况
        "timestamp": "2024-01-15T10:30:00Z",
        "actions_performed": ["add_layer", "take_profit"],
    }
}
```

---

## 8. 策略扩展指南

### 8.1 新增策略步骤

1. **定义配置类**（继承 `StrategyConfig`）
2. **实现策略类**（继承 `Strategy`）
3. **注册 API 路由**（`api/strategies.py`）
4. **添加工厂函数**（`api/deps.py`）

### 8.2 模板代码

```python
from dataclasses import dataclass
from trading_service.strategies.base import Strategy, StrategyConfig

@dataclass
class MyStrategyConfig(StrategyConfig):
    param1: int = 100
    param2: float = 0.5

class MyStrategy(Strategy):
    def __init__(self, exchange, config: MyStrategyConfig, symbol_picker):
        super().__init__(exchange, config, symbol_picker)

    async def execute(self) -> dict:
        """策略核心逻辑"""
        # 1. 获取市场数据
        # 2. 检查当前持仓
        # 3. 生成交易决策
        # 4. 执行交易
        return {"status": "success", "actions": [...]}

    def get_status(self) -> dict:
        """返回策略状态"""
        return {
            "strategy": "my_strategy",
            "config": {...},
            # ...
        }
```

---

## 9. 测试策略

### 9.1 单元测试要点

1. **Mock 外部依赖**：
   - MockExchange → 返回固定持仓
   - MockSymbolPicker → 返回固定币种列表

2. **测试边界条件**：
   - max_layers = 0（禁止加仓）
   - 连续亏损场景
   - 止盈触发场景

3. **验证数据库交互**：
   - 检查 Position 状态变更
   - 验证 Order 记录正确写入

### 9.2 回测支持

> **待实现**：策略引擎应支持回测模式
> - 历史数据回放
> - 无副作用执行
> - 绩效指标输出

---

## 10. 风险控制设计

### 10.1 内置风控机制

| 风控点 | 实现位置 | 说明 |
|--------|----------|------|
| **最大层数限制** | Martingale | 防止无限加仓 |
| **单笔最大仓位** | Strategy 基类 | 限制单笔交易大小 |
| **单日最大亏损** | 待实现 | 单日亏损超过阈值停止 |
| **黑名單币种** | SymbolPicker | 排除高风险币种 |

### 10.2 紧急止损

API 提供手动平仓接口，策略执行也可触发强制平仓：

```python
# 策略内强制止损
if position.pnl_pct(current_price) < -20.0:  # 亏损超 20%
    self.exchange.close_position(position.id, reason="stop_loss")
```
