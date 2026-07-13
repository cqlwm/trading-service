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

    class ISymbolSource {
        <<interface>>
        +fetch() list[SymbolInfo]
    }

    class ISymbolFilter {
        <<interface>>
        +apply(infos) list[SymbolInfo]
    }

    class SelectionPipeline {
        +pick() list[SymbolInfo]
    }

    class AlphaTokenSource {
        +fetch() list[SymbolInfo]
    }

    class TechnicalAnalysisFilter {
        +apply(infos) list[SymbolInfo]
    }

    class ITechnicalAnalyzer {
        <<interface>>
        +detect_200sma_signal() CrossSignal | None
    }

    Strategy --> StrategyConfig
    Strategy --> ISymbolPicker

    Strategy <|-- MartingaleStrategy
    Strategy <|-- MicroCapStrategy
    Strategy <|-- ContentScanStrategy

    StrategyConfig <|-- MartingaleConfig
    StrategyConfig <|-- MicroCapConfig

    ISymbolPicker <|-- StaticListSymbolPicker
    ISymbolPicker <|-- SelectionPipeline
    SelectionPipeline --> ISymbolSource : 编排
    SelectionPipeline --> ISymbolFilter : 编排
    ISymbolSource <|-- AlphaTokenSource
    ISymbolFilter <|-- TechnicalAnalysisFilter
    TechnicalAnalysisFilter --> ITechnicalAnalyzer : 注入
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

## 3. 选币管道

> **模块位置**：`trading_service/pickers/`（统一存放选币管道与技术分析器，禁止放在 `strategies/` 下，由架构契约测试 `tests/architecture/test_contracts.py` 强制守护）

### 3.1 设计动机

选币与技术分析是两个独立的关注点，原先通过 `SimpleAlphaSymbolPicker(enable_technical_filter=True)`
的 bool 开关耦合在一起，导致：选币器背负两个职责、`SymbolInfo` 成为 God Struct、
新增分析阶段只能继续往选币器里塞。重构为 **source -> filter -> 策略** 的管道模式后，
技术分析成为独立、可组合的阶段，选币器回归纯净。

### 3.2 三层抽象

| 抽象 | 职责 | 语义 |
|------|------|------|
| `ISymbolSource` | 数据从哪来 | 生成器：`fetch()` 从无到有产出 `list[SymbolInfo]` |
| `ISymbolFilter` | 怎么处理/增强 | 转换器：`apply(infos)` 接收并返回 `list[SymbolInfo]` |
| `SelectionPipeline` | 编排 source + filters | 实现 `ISymbolPicker.pick()`，对策略层透明 |

> **为何 source/filter 分离而非统一 `ISymbolStage`：** source 是"生成器"语义，
> filter 是"转换器"语义。统一接口会迫使第一个阶段接收空列表、语义别扭。分离后
> 每个接口职责单一，精确映射"选币 -> 技术分析"心智模型。

```python
class ISymbolSource(ABC):
    @abstractmethod
    async def fetch(self) -> list[SymbolInfo]: ...

class ISymbolFilter(ABC):
    @abstractmethod
    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]: ...

class SelectionPipeline(ISymbolPicker):
    def __init__(self, source: ISymbolSource, filters: list[ISymbolFilter] | None = None): ...
    async def pick(self) -> list[SymbolInfo]:
        infos = await self.source.fetch()
        for f in self.filters:
            infos = await f.apply(infos)
        return infos
```

### 3.3 策略层契约（不变）

策略只依赖 `ISymbolPicker.pick()`，与管道实现无关：

```python
class ISymbolPicker(ABC):
    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:
        """筛选符合条件的币种，返回带市场数据与技术指标的 SymbolInfo 列表。"""
```

**设计要点**：
- `pick()` 为 **async** 方法，同步 IO 实现需用 `run_in_executor` 包装
- 返回 `list[SymbolInfo]`（富数据载体），而非裸 `list[str]`
- `SymbolInfo` 定义在 `pickers/base.py`，包含基础字段、Alpha 扩展字段、
  klines（多时间框架 DataFrame）三组。数据源只填基础字段，K 线由各 filter 按需拉取。

### 3.4 实现类

| 类 | 接口 | 数据源 | 用途 |
|----|------|--------|------|
| `StaticListSymbolPicker` | `ISymbolPicker` | 静态字符串列表 | 测试 / DI 占位（Martingale） |
| `AlphaTokenSource` | `ISymbolSource` | 币安 Alpha 代币 API + 合约信息 | 候选集构建（不做交易筛选） |
| `BullishKlineFilter` | `ISymbolFilter` | 1d K 线 | 丢弃式：存入 klines["1d"]，丢弃昨日非阳线 |
| `TechnicalAnalysisFilter` | `ISymbolFilter` | 4h K 线 + `ITechnicalAnalyzer` | 纯增强：存入 klines["4h"]，算 SMA200 指标，不丢弃 |
| `ShortSignalFilter` | `ISymbolFilter` | 读 klines["4h"] | 丢弃式：保留死叉/超买信号 |
| `SelectionPipeline` | `ISymbolPicker` | source + filters 编排 | 组合 source 与 filter，对策略透明 |

**AlphaTokenSource 职责**（只提供候选集，不做交易筛选）：
1. Alpha 代币，市值 5000 万 USDT 以下
2. 在合约交易所存在且处于可交易状态（status=="TRADING", quoteAsset=="USDT"）

> **市值口径**：`circulating_supply × 合约最新价（24h ticker last_price）`，而非直接用现货 `marketCap`。
> 策略实际交易合约，合约价与现货价存在基差，故用合约价算市值更准确。
> `circulating_supply` 缺失或合约价缺失时，降级用现货 `marketCap` 兜底。
> 流程顺序：收集 Alpha 代币 -> 取与可交易合约的交集 -> 批量拉合约 ticker 取价 -> 算市值 -> 过滤 < 阈值（合约价依赖合约存在，故必须先取交集再算市值）。

> MicroCapStrategy 通过 `SelectionPipeline(source=AlphaTokenSource(...), filters=[BullishKlineFilter(...), TechnicalAnalysisFilter(...)])`
> 组合候选集构建与技术分析。MartingaleStrategy 直接用 `StaticListSymbolPicker`。

### 3.5 调用流程

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
    loop 每个 SymbolInfo
        BullishFilter->>Binance: get_future_klines(symbol, "1d", 5)
        Binance-->>BullishFilter: 1d K 线
        Note over BullishFilter: 存入 klines["1d"]，丢弃非阳线
    end
    BullishFilter-->>Pipeline: list[SymbolInfo]（含 klines["1d"]）
    Pipeline->>TechFilter: apply(infos)
    loop 每个 SymbolInfo
        TechFilter->>Binance: get_future_klines(symbol, "4h", 210)
        Binance-->>TechFilter: 4h K 线序列
        TechFilter->>Analyzer: detect_200sma_signal(df)
        Analyzer-->>TechFilter: CrossSignal | None
        Note over TechFilter: 纯增强：写入 klines["4h"]，不丢弃
    end
    TechFilter-->>Pipeline: list[SymbolInfo]（含 klines["1d"] + klines["4h"]）
    Pipeline-->>Strategy: list[SymbolInfo]
```

### 3.6 客户端协议（降低耦合）

`AlphaTokenSource`、`BullishKlineFilter` 与 `TechnicalAnalysisFilter` 不依赖具体的 `BinanceClient`，
而是依赖 `clients/protocols.py` 中定义的结构化协议（Protocol）：

| 协议 | 方法 | 消费者 |
|------|------|--------|
| `KlineClient` | `get_future_klines` | `TechnicalAnalysisFilter`、`BullishKlineFilter` |
| `AlphaUniverseClient` | `get_alpha_tokens` / `get_future_exchange_info` | `AlphaTokenSource` |
| `MarketDataClient` | 上述两者的超集 | 需要全部能力的消费者 |

`BinanceClient` 在结构上满足这些协议，无需显式继承；测试可注入内存实现（duck typing）。

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
- 通过**依赖注入**提供给 `TechnicalAnalysisFilter`（构造函数 `analyzer` 参数），便于单元测试替换 mock
- `TechnicalAnalyzer` 是默认实现，提供 SMA 计算、200 均线穿越信号检测、底部横盘判定
- 所有计算方法无状态，可安全共享单例
- `TechnicalAnalysisFilter` 是**纯增强**：analyzer 返回 None 时 SymbolInfo 数量不减、klines DataFrame 不含信号列；买入信号判定由策略负责
- 所有技术指标统一由 `klines` DataFrame 承载，`SymbolInfo` 不持有冗余快照字段。检测器、过滤器、策略均从 DataFrame 最后一行读取指标

### 4.2 信号类型

`CrossSignal` 数据结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `cross_type` | `CrossSignalType` | `GOLDEN`(金叉) / `DEAD`(死叉) / `NEAR`(靠近均线) |
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
- `cross_signal == CrossSignalType.GOLDEN`：金叉，收盘价从下向上突破 200 均线（近期突破）

> 选币与技术分析由 `SelectionPipeline(source=AlphaTokenSource, filters=[TechnicalAnalysisFilter])` 完成，策略只消费 `SymbolInfo.klines` DataFrame 中的指标。

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
2. **选币**：`symbol_picker.pick()` 返回候选 `SymbolInfo`（已含 klines DataFrame）
3. **过滤**：排除已持仓 symbol；只保留 `_is_buy_signal` 通过的
4. **开仓**：按 `max_positions - current_count` 配额，对候选开多仓
   - `size = position_size_usdt`（10 USDT）
   - `reason_text` 为自然语言描述（如"开仓 @ {price}"），`reason_data` 为结构化决策数据（含 `action`、`cross_signal`、`price`、`size`）
   - 决策上下文写入 `trading_strategy_actions` 表，通过 `order_id` 关联订单

> 止盈/止损、调仓换仓留待后续迭代。

---

## 7. 信号检测器（SignalDetector）

信号检测器是**策略的组件**，由策略在 execute() 内部调用。检测器接收策略选好的候选币列表进行信号检测，产出的信号落盘到 `trading_signals` 表。

### 7.1 设计定位

```
调度器（cron）
  └─ 策略（唯一调度对象）
       ├─ 1. 选币：symbol_picker.pick() -> list[SymbolInfo]
       ├─ 2. 信号检测：detectors.detect(candidates) -> 信号落盘
       └─ 3. 决策：基于信号做交易 -> 动作记录（含 signal_ids）+ 订单
```

- **检测器是策略组件**：不独立调度，由策略在选币后调用
- **检测器不管选币**：接收策略传入的候选币列表（已含技术分析字段）
- **信号可不被消费**：内容型信号（如连涨3日）只落盘，供 LLM 生成贴文
- **策略自动幂等**：持仓检查（tag 隔离 + status 过滤）天然防止重复交易

### 7.2 信号检测器基类

```python
class SignalDetector(ABC):
    name: str = ""  # 检测器标识

    def __init__(self, repo: TradingRepository) -> None: ...

    @abstractmethod
    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]: ...

    def get_status(self) -> dict[str, Any]: ...
```

### 7.3 策略基类的检测器支持

```python
class Strategy(ABC):
    def __init__(self, exchange, config, symbol_picker, signal_detectors=None): ...

    async def run_detectors(self, candidates, execution_id="") -> list[SignalRecord]:
        """运行所有检测器，信号落盘并返回。"""
```

### 7.4 已实现的检测器

| 检测器 | name | 产出信号 |
|--------|------|----------|
| 技术分析信号检测器 | `technical_signal` | `golden_cross`（金叉）、`dead_cross`（死叉）、`sideways_bottom`（底部横盘）|

### 7.5 新增信号检测器步骤

1. 继承 `SignalDetector`，设 `name` 类属性
2. 实现 `detect(candidates)` 方法，接收 `list[SymbolInfo]`，返回 `list[SignalResult]`
3. 在 `api/deps.py` 实例化，通过策略构造函数 `signal_detectors=[...]` 注入

---

## 8. 策略执行流程

### 8.1 通用执行流程

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

### 8.2 策略触发方式

| 触发方式 | 说明 | 实现 |
|----------|------|------|
| **API 触发** | 显式调用策略接口 | `POST /api/strategies/{name}/execute` |
| **定时调度** | 调度器 cron 定时触发 | `StrategyScheduler._execute_strategy` |

---

## 9. 策略状态报告

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
    self.exchange.close_position(
        position.id,
        reason_text=f"止损平仓 @ {current_price}",
        reason_data={"action": "stop_loss", "price": current_price, "loss_pct": 20.0},
    )
```

---

## 11. 贴文自动生成

### 11.1 接口架构

贴文生成采用接口 + 可插拔风格模式：

```
IPostGenerator (ABC)
  └─ generate_for_execution(execution_id) -> list[Path]

PostGenerator (IPostGenerator)
  ├─ 共享基础设施：LLM 调用 / 文件保存 / 历史贴文加载
  ├─ _styles: dict[str, PostStyle]  ← 按 action_type 分发
  └─ generate_for_execution():
       读 actions -> 按 action_type 选 style
       -> style.build_context() -> style.build_prompt()
       -> _call_llm() -> _save_post()

PostStyle (ABC)
  ├─ action_type: str                    ← 匹配标识
  ├─ build_context(repo, actions, ...)   ← 构建上下文
  └─ build_prompt(context)               ← 构建 LLM prompt
```

### 11.2 两种 PostStyle

| 风格 | action_type | 上下文 | prompt 角色 | 触发策略 |
|------|------------|--------|------------|---------|
| `TradingPostStyle` | "trading" | 交易故事线 + 持仓 + 历史贴文 | 交易员 | 马丁做空等（open/add/close） |
| `ContentPostStyle` | "content" | 信号详情 + 历史贴文 | 市场观察者 | ContentScanStrategy（content） |

加新风格只需继承 `PostStyle`，实现 `action_type`/`build_context`/`build_prompt`，构造时传入 `styles=[...]`。

### 11.3 触发机制

```
策略执行完成（定时 _execute_strategy / 手动 execute_strategy_manually）
  └─ actions 非空？
     ├─ 否 -> 跳过
     └─ 是 -> post_generator.generate_for_execution(execution_id)
        （try/except 包裹，失败不影响策略执行）
```

两条执行路径（定时 + 手动）都接入了贴文生成。

### 11.4 内容型策略 ContentScanStrategy

每 10 分钟从涨幅榜选币，检测连续涨跌K线，选 1 条生成贴文：

```
ContentScanStrategy.execute()
  ├─ 1. 选币：TopGainersSource（24h ticker 涨幅榜 top 20）
  ├─ 2. 信号检测：ConsecutiveCandleDetector（拉 1d K 线，连续涨/跌 >= 3 天）
  ├─ 3. run_detectors -> 信号落盘到 trading_signals
  ├─ 4. 选 severity 最高的 1 条信号
  ├─ 5. 写 action_type="content" 动作记录（含 signal_ids）
  └─ 6. 返回 [StrategyAction(type="content")]
     -> scheduler 检测到 actions 非空 -> 触发 PostGenerator
     -> PostGenerator 检测到 content 类型 -> 走 ContentPostStyle
     -> 市场观察者角色 prompt -> LLM 生成贴文
```

不开仓、不平仓，纯内容产出。
