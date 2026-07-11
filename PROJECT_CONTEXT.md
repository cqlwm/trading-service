# ================================================================
# 🧠 项目上下文记忆 - 每次开发前必须阅读！
# ================================================================

# -----------------------
# 📁 核心目录职责
# -----------------------
trading_service/
├── pickers/           # ✅ 选币管道统一放在这里！不要再创建symbol_picker.py了！
│   ├── base.py                  # 核心契约：SymbolInfo / ISymbolPicker / StaticListSymbolPicker
│   ├── pipeline.py              # ISymbolSource / ISymbolFilter / SelectionPipeline 编排器
│   ├── symbol_picker.py         # AlphaTokenSource 数据源（基础选币，不含技术分析）
│   ├── technical_analyzer.py    # ITechnicalAnalyzer / TechnicalAnalyzer 技术分析工具
│   ├── technical_filter.py      # TechnicalAnalysisFilter（纯增强技术阶段）
│   ├── signal.py                # 信号判定纯函数：is_notable_signal / is_delisting_soon
│   ├── short_signal_filter.py   # 做空信号过滤器（死叉/远离均线）
│   └── backtest.py              # 回测核心逻辑：simulate_trade / simulate_portfolio / summarize
│
├── detectors/         # ✅ 信号检测器（与策略平行，由调度器定时调度）
│   ├── base.py                  # SignalDetector 基类 / SignalResult 数据类
│   └── technical.py             # TechnicalSignalDetector（金叉/死叉/横盘信号检测）
│
├── clients/           # 外部API客户端（币安等）
│   ├── binance_client.py        # BinanceClient（同步阻塞IO，非async）
│   └── protocols.py             # KlineClient / MarketDataClient 协议（结构化类型）
│
├── strategies/        # 交易策略
│   ├── base.py                  # Strategy 基类 + StrategyAction + StrategyConfig
│   ├── martingale.py            # 马丁格尔做多策略
│   ├── martingale_short.py      # 马丁格尔做空策略（继承做多）
│   └── micro_cap.py             # 微市值策略（信号驱动：从 DB 拉取金叉信号决策）
│
├── repository/        # 数据持久化层
│   ├── abc.py                   # Record dataclass + TradingRepository 抽象接口
│   ├── sqlalchemy_impl.py       # SQLAlchemy 实现
│   └── models/                  # ORM 模型
│       ├── position.py          # trading_positions
│       ├── order.py             # trading_orders（无 reason 字段）
│       ├── signal.py            # trading_signals
│       ├── schedule.py          # trading_strategy_schedules + trading_strategy_executions
│       └── action.py            # trading_strategy_actions（动作记录，含 signal_ids）
│
├── api/               # API 层
│   ├── deps.py                  # 依赖注入（策略+检测器+调度器全局单例装配）
│   ├── positions.py             # 持仓 API
│   ├── orders.py                # 订单 API（无 reason 字段）
│   ├── signals.py               # 信号 API（支持 signal_type 过滤）
│   ├── strategies.py            # 策略 API（执行/调度/执行历史）
│   ├── detectors.py             # 检测器 API（start/stop/execute/list）
│   └── timeline.py              # 时间线 API
│
├── exchange.py        # Mock交易所实现（开仓/加仓/平仓 均写入动作记录）
├── scheduler.py       # 策略调度器（统一管理策略+检测器的定时调度）
└── config.py

frontend/              # ✅ 前端独立项目（React 19 + Vite 8 + TS + TanStack Query）
├── src/
│   ├── api/client.ts           # 统一 fetch 封装（超时/错误归一化）
│   ├── types/index.ts          # 镜像后端枚举与模型（含 PaginatedResponse）
│   ├── hooks/                  # TanStack Query 数据层（usePositions/useOrders/...）
│   ├── components/             # ui/ + layout/ + positions/ + strategies/ + dashboard/
│   ├── pages/                  # 6 页：Dashboard/Positions/Orders/Signals/Strategies/Timeline
│   └── lib/                    # constants(端点+轮询) / format(容错格式化) / cn
├── vite.config.ts     # /api 代理到 127.0.0.1:8001
└── tailwind.config.js # 暗色主题 + shadcn CSS 变量体系

demo/                   # 展示/运维脚本（不进 pyright/测试）
├── demo_picker.py               # 基础选币演示
├── demo_technical_picker.py     # 技术分析选币（含下架预警展示）
├── demo_backtest.py             # 止盈率回测（资金约束，日级调度）
└── demo_take_profit.py          # 为真实持仓批量下限价止盈单（ccxt鉴权，真实资金）

# -----------------------
# 🔗 接口契约（CRITICAL!）
# -----------------------

## ISymbolPicker 接口
class ISymbolPicker(ABC):
    @abstractmethod
    async def pick(self) -> list[SymbolInfo]:  # ✅ 必须是 async！
        ...

## SymbolInfo 数据契约（所有字段都在这里扩展，不要再分散定义！）
@dataclass
class SymbolInfo:
    # 基础字段
    symbol: str
    price: float = 0.0
    volume_24h: float = 0.0
    market_cap: float = 0.0
    price_change_pct_24h: float = 0.0
    # Alpha扩展字段
    base_asset: str = ""
    yesterday_change_percent: float = 0.0
    # 技术分析字段（TechnicalAnalysisFilter 回填）
    sma_200: float | None = None
    cross_signal: CrossSignalType | None = None
    is_sideways_bottom: bool = False
    volatility_10: float | None = None
    # 合约生命周期字段（AlphaTokenSource 从 exchangeInfo 回填）
    delivery_date: int | None = None  # 永续正常=哨兵值，即将下架=具体时点(ms)
    # ...

## 信号判定纯函数（pickers/signal.py）
- is_notable_signal(info) -> bool：金叉/靠近均线/横盘返回True，死叉/None返回False
- is_delisting_soon(info) -> bool：delivery_date偏离哨兵值即True（即将下架）
- PERPETUAL_DELIVERY_SENTINEL = 4133404800000（哨兵常量，定义在 symbol_picker.py）
- 注意：这些是纯函数，操作内存 SymbolInfo。与 trading_signals 表无关。
  trading_signals 表的信号由信号检测器（detectors/）产出落盘。

## 信号检测器（detectors/）
- SignalDetector 基类：与策略平行，由调度器定时调度，产出 SignalResult 落盘
- TechnicalSignalDetector：产出 golden_cross/dead_cross/sideways_bottom 信号
- 策略通过 `get_recent_signals(signal_type=...)` 从 DB 拉取信号做决策
- 信号可不被消费（内容型信号只落盘，供 LLM 生成贴文）

## 回测核心逻辑（pickers/backtest.py）
- simulate_trade(...)：单笔模拟（无资金约束），逐日判定止盈/下架/未决
- simulate_portfolio(...)：日级资金调度（100U/10仓约束），按日推进维护资金池
- _check_position_on_day(...)：共享原语，单笔仓位某日是否触发止盈/下架
- PortfolioConfig(total_capital=100, position_size=10, max_positions=10)
- 二元盈亏结构：赢 +10×TP%，输 ≈ -10×loss_pct（下架清算，非精确-100%）

# -----------------------
# 🌐 前后端 API 协议（2026-07-11 重构后）
# -----------------------

## 统一分页格式
所有列表端点返回 `{data: [...], total: N}`（不是裸数组！不是文档里的旧格式！）
- Repository 层有 count_positions/count_orders/count_signals 方法
- 前端用 useInfiniteQuery，以 loaded >= total 判断是否到底

## 端点与参数（以实际代码为准，非 architecture_document/05-api-design.md）
| 端点 | 关键点 |
|------|--------|
| GET /api/positions | 仅支持 `status` 参数；列表含 current_price/pnl_pct/source/layers |
| GET /api/positions/{id} | 详情**不含** current_price/pnl_pct；orders **不含** reason 字段 |
| POST /api/positions/{id}/close | 无请求体；响应不含 reason（reason 已移至动作记录） |
| GET /api/orders | 参数 `symbol`/`order_type`/`limit`/`offset`；**不含** reason 字段 |
| GET /api/signals | 参数名 `severity_min` + `signal_type`（新增）；信号由 Trading Service 检测器产出 |
| POST /api/strategies/*/execute | 通过调度器执行，返回 `{execution_id, actions:[{type,symbol,reason}], action_count}` |
| GET /api/strategies/*/executions | 执行历史含 actions，每个 action 有 `signal_ids` 关联信号 |
| GET /api/strategies/*/status | 含完整 config 字段（含 stop_loss_pct 等）+ schedule |
| GET /api/detectors | 列出所有信号检测器状态 |
| POST /api/detectors/{name}/start|stop|execute | 检测器启停和手动执行 |
| GET /api/timeline | 信号+订单混排（不含 reason） |

## direction 语义区分（不要混用！）
- Position/Order.direction: `long` / `short`（TradeDirection 枚举）
- Signal.direction: `bullish` / `bearish` / `neutral`（MarketDirection 枚举）

## 策略 execute 契约（2026-07-11 重构后）
- `Strategy.execute(execution_id="")` 返回 `list[StrategyAction]`
- `StrategyAction = dataclass(type, symbol, reason)`，type: "open"/"add"/"close"/"skip"
- `reason` 字段（原 `detail`）是决策描述，与动作记录的 `reason_text` 语义统一
- execution_id 透传给 exchange，关联动作记录到调度轮次

## 三层事件流架构（2026-07-11 重构核心设计）
```
观察层（信号）         决策层（动作）         事实层（订单）
SignalRecord    ->    StrategyActionRecord  ->   OrderRecord
（trading_signals）   （trading_strategy_actions）（trading_orders）
```
- **信号**：由信号检测器产出落盘，策略主动拉取消费，也可不被消费（内容生成用）
- **动作记录**：MockExchange 在开仓/加仓/平仓时写入，含 reason_text + reason_data + signal_ids
- **订单**：纯交易事实（不含 reason，reason 已移至动作记录）
- **故事线**：`list_actions_by_position` / `list_actions_by_symbol` 按时间正序返回完整交易故事

# -----------------------
# ⚠️ 常见陷阱检查清单（踩过的坑！）
# -----------------------
1. ❌ 不要再在 strategies/ 下创建 symbol_picker.py！统一在 pickers/
2. ❌ ISymbolPicker.pick() 必须是 async！不要写成同步！
3. ❌ 不要在 __init__.py 里写逻辑，只做导出
4. ✅ pyright 0 errors 0 warnings 通过才算完成
5. ✅ 所有新类都要考虑：是给策略框架用的吗？如果是就要async兼容
6. ✅ BinanceClient 是同步的，如果要在 async pick() 里用，必须套线程池
7. ✅ K线数据类是 BinanceFutureKline，不是 KLine 或其他名字
8. ✅ 所有 enum 定义在 types.py，不要分散定义
9. ⚠️ deliveryDate 哨兵值陷阱：永续合约 deliveryDate=4133404800000（2100-12-25）
   表示"永不到期"；即将下架时 Binance 会改成具体时点（提前约15天）。
   判定下架用 is_delisting_soon()，不要自己比较数字！
   注意：ccxt 会把永续/哨兵值的 expiry 置 None 丢弃，但我们用 Pydantic
   直接建模原始字段（BinanceFutureSymbol.delivery_date），能拿到真值。
10. ⚠️ TechnicalAnalysisFilter 是「纯增强不丢弃」设计（有测试保护的不变量）：
    死叉(DEAD)和无信号(None)的代币都会保留，只回填技术字段。
    展示层/策略层按需用 is_notable_signal() 过滤，不要改 filter 本身！
11. ⚠️ 回测生存者偏差（未解决）：候选池是「当前仍在交易的」代币，
    已下架的币不在候选池里 -> loss 永远为0 -> 胜率虚高100%。
    回测的绝对盈亏不可信，只有相对结论（TP之间比较）有参考价值。
12. ⚠️ 回测资金约束：simulate_portfolio 按100U/10仓约束，止盈释放资金可复用，
    下架不释放。同一代币可叠加加仓。不要用 simulate_trade 做资金约束回测！

# -----------------------
# 🏗️ 三层事件流 + 信号检测器架构（2026-07-11 重构）
# -----------------------
21. ⚠️ Order 表**不含** reason 字段！下单原因（决策上下文）已移至
    `trading_strategy_actions` 表的 `reason_text` + `reason_data`。
    不要在 OrderRecord/OrderModel 上加回 reason！
22. ⚠️ `StrategyExecutionRecord` **不含** `actions_json`！动作记录已拆到独立的
    `trading_strategy_actions` 表，通过 `execution_id` 关联到轮次记录。
    API 层负责 join 查询。
23. ⚠️ 信号检测器（SignalDetector）与策略（Strategy）是**平行**的，不继承 Strategy！
    - 检测器产出 SignalResult（观察），策略产出 StrategyAction（交易）
    - 检测器只依赖 repo（写信号），不需要 exchange/symbol_picker
    - 检测器在 deps.py 中传入 `StrategyScheduler(detectors=[...])`
24. ⚠️ 微市值策略（MicroCapStrategy）**不再用 SymbolPicker 做信号过滤**！
    策略从 DB 拉取 `golden_cross` 信号做决策。SymbolPicker 仍作为基类依赖传入，
    但 execute() 内不调用 picker.pick()。
25. ⚠️ 动作记录的 `signal_ids: list[str]` 可以关联多个信号（一个决策可基于多信号）。
    策略持仓检查（tag 隔离 + status 过滤）天然防止重复交易，不需要信号层防重复。
26. ⚠️ `sqlalchemy_impl.py` 的 `metadata_json` 读取时必须 `json.loads`（曾漏掉，已修复）。
    `_signal_model_to_record` / `_action_model_to_record` 中所有 JSON 字段都要反序列化。
27. ⚠️ 手动执行策略也产生执行记录！走 `scheduler.execute_strategy_manually()`，
    不再直接调 `strategy.execute()`。手动执行也有 execution_id 关联动作记录。

# -----------------------
# 📈 币安合约下单陷阱（真实资金操作！踩过3个坑）
# -----------------------
13. ⚠️ BinanceClient 是纯只读市场数据客户端，无 apiKey/secret、无下单能力。
    真实下单用独立 demo 脚本（demo/demo_take_profit.py）+ ccxt 鉴权实例，
    不要把交易能力混进 BinanceClient！
14. ⚠️ 双向持仓模式(hedge mode)的3个连环坑（账户开了多空双开）：
    a) fetch_positions 返回 ccxt 统一格式 symbol（如 PUMPBTC/USDT:USDT），
       不是币安原生格式（PUMPBTCUSDT）。过滤/比较时要归一化去 / 和 :。
    b) 下单必须传 positionSide（LONG/SHORT），否则报 -4061。
       从 position.info.positionSide 取，单向模式是 BOTH，双向是 LONG/SHORT。
    c) reduceOnly 和 positionSide(非BOTH) 互斥！双向模式传 reduceOnly 报 -1106。
       规则：positionSide==BOTH 时才传 reduceOnly，双向模式靠 positionSide 定向。
15. ⚠️ 币安合约订单类型区别（USDT-M futures）：
    - LIMIT: 普通限价单，直接挂订单簿，price+amount+timeInForce。无触发条件。
      多头止盈价已低于市价时会立即成交（非真正的"等触发"）。
    - TAKE_PROFIT: 限价条件止盈单，stopPrice(触发)+price(限价)+amount。先触发才挂单。
    - TAKE_PROFIT_MARKET: 市价条件止盈单，stopPrice+closePosition(整仓)。

# -----------------------
# 🔧 前后端联调踩过的坑（2026-07-10）
# -----------------------
16. ⚠️ fetch_prices() 曾经是空实现（返回全 0.0），导致：
    - 持仓盈亏全是 -100%（(0-entry)/entry*100）
    - 策略开仓条件 `if price > 0` 永远不满足，策略执行无效
    已修复：用 ccxt 同步调用 Binance 现货 fetch_tickers 获取真实价格。
17. ⚠️ ccxt 4.5.64 的 fetch_tickers / close 是**同步方法**，不是协程！
    不要 `await exchange.fetch_tickers(...)`，会报 'dict' object can't be awaited。
    fetch_prices 虽然是 async def，但内部直接同步调用 ccxt 即可。
18. ⚠️ config.yaml 里 db_path: "~/projects/db/news.db" 的 `~` 不会被 SQLAlchemy 展开！
    必须在 config.py 里 `settings.db_path = str(Path(settings.db_path).expanduser())`。
    否则报 sqlite3.OperationalError: unable to open database file。
19. ⚠️ FastAPI 依赖注入：`ExchangeDep = Annotated[MockExchange, Depends(get_exchange)]`
    使用时直接 `exchange: ExchangeDep` 即可，**不要**再包 `Depends(ExchangeDep)`！
    `Depends(ExchangeDep)` 会把 Annotated 类型当 callable 调用，报 "Field required: args, kwargs"。
    如果参数前面有带默认值的参数（如 offset=0），无默认值参数不能跟在后面，
    此时用 `exchange: MockExchange = Depends(get_exchange)` 方式。
20. ⚠️ 符号格式不统一曾导致价格取不到：
    - DB 存储/策略层用 binance 原生格式（BTCUSDT）
    - ccxt 用斜杠格式（BTC/USDT）
    - fetch_prices 现在内部用 Symbol.parse() 归一化，统一以 binance 格式为 key 返回
    - positions.py 不要再把 symbol 转 ccxt 格式去查 prices dict！直接用 p.symbol。

# -----------------------
# 📝 命名约定
# -----------------------
- 类名: PascalCase (AlphaTokenSource, SelectionPipeline, BinanceFutureKline)
- 方法/函数: snake_case (pick, _pick_sync, get_future_klines)
- 私有方法: 下划线前缀 (_pick_sync, _analyze_symbol)
- 测试文件: test_*.py

# -----------------------
# 🚀 开发命令
# -----------------------
## 后端
uv run python main.py                    # 启动 :8001
.venv/bin/pyright                        # 类型检查（必须 0 errors）
.venv/bin/python -m pytest tests/ -q     # 测试（256 passed, ~1.6s）
.venv/bin/alembic upgrade head           # 执行数据库迁移
.venv/bin/alembic revision --autogenerate -m "描述"  # 生成迁移脚本

## 前端（frontend/ 目录下）
npm run dev                              # 启动 :5173，代理 /api -> :8001
npx tsc --noEmit -p tsconfig.app.json    # 类型检查
npm run build                            # 生产构建

# -----------------------
# 📌 关于这个文件
# -----------------------
为什么叫 PROJECT_CONTEXT.**md** 而不是 .yaml？
→ 这是**给 LLM 读的"项目记忆文件"**，不是给程序读的配置。
→ Markdown 的可读性和表达力都比纯 YAML 更适合描述架构约定和陷阱。
→ **每次让我开发新功能前，请先让我读这个文件！**
