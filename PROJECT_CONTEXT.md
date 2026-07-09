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
│   └── technical_filter.py      # TechnicalAnalysisFilter（纯增强技术阶段）
│
├── clients/           # 外部API客户端（币安等）
│   ├── binance_client.py        # BinanceClient（同步阻塞IO，非async）
│   └── protocols.py             # KlineClient / MarketDataClient 协议（结构化类型）
│
├── strategies/        # 交易策略
│   ├── BaseStrategy  # 所有策略基类，async框架
│   ├── MartingaleStrategy
│   └── MicroCapStrategy
│
├── repository/        # 数据持久化层
├── exchange.py        # Mock交易所实现
└── config.py

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
    # 技术分析字段
    sma_200: float | None = None
    cross_signal: str | None = None
    is_sideways_bottom: bool = False
    # ...

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

# -----------------------
# 📝 命名约定
# -----------------------
- 类名: PascalCase (AlphaTokenSource, SelectionPipeline, BinanceFutureKline)
- 方法/函数: snake_case (pick, _pick_sync, get_future_klines)
- 私有方法: 下划线前缀 (_pick_sync, _analyze_symbol)
- 测试文件: test_*.py

# -----------------------
# 📌 关于这个文件
# -----------------------
为什么叫 PROJECT_CONTEXT.**md** 而不是 .yaml？
→ 这是**给 LLM 读的"项目记忆文件"**，不是给程序读的配置。
→ Markdown 的可读性和表达力都比纯 YAML 更适合描述架构约定和陷阱。
→ **每次让我开发新功能前，请先让我读这个文件！**
