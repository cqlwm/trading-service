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
        +pick() list[SymbolInfo]
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

    class StaticListSymbolPicker {
        +pick() list[SymbolInfo]
    }

    class SimpleAlphaSymbolPicker {
        +pick() list[SymbolInfo]
    }

    class ITechnicalAnalyzer {
        <<interface>>
        +detect_200sma_signal() CrossSignal | None
    }

    Strategy --> StrategyConfig
    Strategy --> ISymbolPicker

    Strategy <|-- MartingaleStrategy
    Strategy <|-- MicroCapStrategy

    StrategyConfig <|-- MartingaleConfig
    StrategyConfig <|-- MicroCapConfig

    ISymbolPicker <|-- StaticListSymbolPicker
    ISymbolPicker <|-- SimpleAlphaSymbolPicker
    SimpleAlphaSymbolPicker --> ITechnicalAnalyzer : 注入
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

> **模块位置**：`trading_service/pickers/`（统一存放所有选币器与技术分析器，禁止放在 `strategies/` 下，由架构契约测试 `tests/architecture/test_contracts.py` 强制守护）

### 3.1 ISymbolPicker 接口

```python
class ISymbolPicker(ABC):
    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:
        """筛选符合条件的币种，返回带市场数据与技术指标的 SymbolInfo 列表。"""
```

**设计要点**：
- `pick()` 为 **async** 方法，同步 IO 实现需用 `run_in_executor` 包装
- 返回 `list[SymbolInfo]`（富数据载体），而非裸 `list[str]`
- `SymbolInfo` 定义在 `pickers/symbol_picker.py`，包含基础字段、Alpha 扩展字段、技术分析字段三组

### 3.2 实现类

| 实现类 | 数据源 | 用途 |
|--------|--------|------|
| `StaticListSymbolPicker` | 静态字符串列表 | 测试 / DI 占位 |
| `SimpleAlphaSymbolPicker` | 币安 Alpha 代币 API + 合约 K 线 | 真实选币（马丁格尔、微市值均复用），可选叠加技术分析 |

> MicroCapStrategy 不再拥有专属选币器，复用 `SimpleAlphaSymbolPicker(enable_technical_filter=True)`。

**SimpleAlphaSymbolPicker 筛选条件**：
1. Alpha 代币，市值 5000 万 USDT 以下
2. 在合约交易所存在且处于可交易状态（status=="TRADING", quoteAsset=="USDT"）
3. 昨日 K 线为阳线（收盘价 >= 开盘价）
4. [可选] 200 均线附近，底部横盘或刚突破（通过 `ITechnicalAnalyzer`）

### 3.3 调用流程

```mermaid
sequenceDiagram
    participant Strategy as Strategy
    participant Picker as SimpleAlphaSymbolPicker
    participant Analyzer as ITechnicalAnalyzer
    participant Binance as BinanceClient

    Strategy->>Picker: pick()
    Picker->>Binance: get_alpha_tokens() + get_future_exchange_info()
    Binance-->>Picker: Alpha 代币 + 可交易合约
    Picker->>Picker: 取交集 + 市值过滤
    Picker->>Binance: get_future_klines(symbol, "1d")
    Binance-->>Picker: 昨日 K 线
    Picker->>Picker: 阳线过滤
    opt enable_technical_filter
        Picker->>Binance: get_future_klines(symbol, interval, 210)
        Binance-->>Picker: K 线序列
        Picker->>Analyzer: detect_200sma_signal(klines)
        Analyzer-->>Picker: CrossSignal | None
    end
    Picker-->>Strategy: list[SymbolInfo]
```

---

## 4. 技术分析器

### 4.1 ITechnicalAnalyzer 接口

```python
class ITechnicalAnalyzer(ABC):
    @abstractmethod
    def detect_200sma_signal(
        self,
        klines: list[BinanceFutureKline],
        symbol: str,
        check_last_n: int = 10,
        near_threshold: float = 5.0,
        sideways_threshold: float = 20.0,
    ) -> CrossSignal | None:
        """检测 200 均线穿越信号（金叉/死叉/靠近均线）。"""
```

**设计要点**：
- 通过**依赖注入**提供给 `SimpleAlphaSymbolPicker`（构造函数 `analyzer` 参数），便于单元测试替换 mock
- `TechnicalAnalyzer` 是默认实现，提供 SMA 计算、200 均线穿越信号检测、底部横盘判定
- 所有计算方法无状态，可安全共享单例

### 4.2 信号类型

`CrossSignal` 数据结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `cross_type` | str | "golden"(金叉) / "dead"(死叉) / "near"(靠近均线) |
| `cross_ago` | int | 多少根 K 线前发生的穿越（0 为刚发生） |
| `sma_200` | float | 200 均线价格 |
| `distance_percent` | float | 价格相对均线的距离百分比 |
| `volatility_10` | float | 最近 10 根 K 线波动率 |
| `is_sideways` | bool | 是否处于底部横盘 |

### 4.3 优先级

信号检测优先级：**金叉/死叉穿越 > 靠近均线**。无穿越且远离均线（距离 > near_threshold）时返回 `None`。

---

## 5. 马丁格尔策略 (Martingale)

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

## 6. 微市值策略 (MicroCap)

### 5.1 策略原理

```mermaid
graph TD
    A[SymbolPicker 选币<br/>市值<5000万 + 昨日上涨] --> B[技术分析过滤]
    B --> C{横盘 或 金叉突破?}
    C -->|是| D[买入 position_size_usdt]
    C -->|否| E[不操作]
    D --> F{已达 max_positions?}
    F -->|是| G[停止开仓]
    F -->|否| H[继续下一个候选]
```

**买入信号判定**（`_is_buy_signal`）：
- `is_sideways_bottom == True`：底部横盘（低波动 + 价格在 200 均线上方）
- `cross_signal == "golden"`：金叉，收盘价从下向上突破 200 均线（近期突破）

> 选币与技术分析由 `SimpleAlphaSymbolPicker(enable_technical_filter=True)` 完成，策略只消费 `SymbolInfo` 的技术字段。

### 5.2 配置参数 (MicroCapConfig)

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `max_positions` | int | 10 | 最大同时持仓数 |
| `position_size_usdt` | float | 10.0 | 单笔买入金额（USDT） |
| `take_profit_pct` | float | 5.0 | 止盈百分比（下一轮实现） |
| `stop_loss_pct` | float | 15.0 | 止损百分比（下一轮实现） |
| `min_volume_usdt` | float | 1,000,000 | 最低 24h 成交量（由选币器使用） |
| `max_market_cap` | float | 50,000,000 | 最大市值（由选币器使用） |

### 5.3 入场逻辑

1. **检查配额**：当前 `tag="micro_cap"` 的 open 持仓数 >= `max_positions` 则直接返回
2. **选币**：`symbol_picker.pick()` 返回候选 `SymbolInfo`（已含技术分析字段）
3. **过滤**：排除已持仓 symbol；只保留 `_is_buy_signal` 通过的
4. **开仓**：按 `max_positions - current_count` 配额，对候选开多仓
   - `size = position_size_usdt`（10 USDT）
   - `reason` 区分 `micro_cap_entry_sideways` / `micro_cap_entry_breakout`

> 止盈/止损、调仓换仓留待后续迭代。

---

## 7. 策略执行流程

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

## 8. 策略状态报告

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

## 9. 策略扩展指南

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

## 10. 测试策略

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

## 11. 风险控制设计

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
