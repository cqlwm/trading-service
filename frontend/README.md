# Trading Service 前端

Trading Service 的 Web 管理界面，提供持仓监控、订单流水、信号监控、策略控制和交易时间线等功能。

## 技术栈

- **React 19** + **TypeScript**（严格类型检查）
- **Vite 8** 开发与构建
- **TanStack Query 5** 数据获取与缓存（加载更多分页、定时轮询、mutation 联动刷新）
- **React Router 7** 路由
- **Tailwind CSS 3** 暗色主题 UI
- **shadcn/ui 风格**手写基础组件
- **Sonner** Toast 通知
- **Lucide** 图标

## 快速开始

### 前置条件

1. 后端 Trading Service 运行在 `http://127.0.0.1:8001`（启动方式见项目根目录 README）
2. Node.js 18+

### 安装与启动

```bash
cd frontend
npm install
npm run dev
```

前端运行在 `http://localhost:5173`，API 请求通过 Vite 代理转发到后端 8001 端口。

### 构建

```bash
npm run build      # 类型检查 + 生产构建，产物在 dist/
npm run preview    # 预览生产构建
```

## 功能模块

| 模块 | 路径 | 功能 |
|------|------|------|
| 仪表盘 | `/` | 持仓统计、策略状态、最近信号与订单 |
| 持仓 | `/positions` | 持仓列表（状态筛选）、详情抽屉、手动平仓 |
| 订单 | `/orders` | 订单流水，按交易对/类型筛选，加载更多 |
| 信号 | `/signals` | 市场信号监控，按严重度筛选，加载更多 |
| 策略 | `/strategies` | 马丁/微市值策略状态与执行，历史记录 |
| 时间线 | `/timeline` | 信号+订单混合事件流，5 秒自动刷新 |

## 架构

```
src/
├── api/client.ts        # 统一 fetch 封装（超时、错误归一化）
├── types/index.ts       # 镜像后端枚举与领域模型
├── hooks/               # TanStack Query 数据层（查询 + mutation）
├── components/
│   ├── ui/              # 基础组件（Button/Card/Badge/Table/Drawer...）
│   ├── layout/          # AppShell 侧边栏 + 页面头部
│   ├── positions/       # 持仓表格 + 详情抽屉
│   ├── strategies/      # 策略卡片
│   └── dashboard/       # 统计卡片
├── pages/               # 6 个页面
└── lib/                 # 工具函数（格式化、常量、cn）
```

### 数据刷新策略

- **持仓页**：5 秒轮询 + 平仓/策略执行后自动刷新
- **时间线页**：5 秒轮询
- **策略状态**：5 秒轮询
- **订单/信号页**：进入刷新 + 加载更多
- **策略执行**：成功后自动刷新持仓、订单、策略状态、时间线

### 与后端 API 的对齐说明

前端类型严格镜像后端 `trading_service/types.py` 枚举与领域模型。以下是与后端实现对齐的关键点（注意：部分行为与架构文档描述不同，前端以**实际代码**为准）：

1. **列表接口返回裸数组**：所有列表端点返回 `[]` 而非 `{data, total}` 包裹结构，分页使用加载更多模式（无 `total` 字段，以返回长度 < `limit` 判断到底）
2. **价格占位容错**：后端 `fetch_prices()` 当前为占位实现返回 0，导致 open 持仓的 `current_price` 和 `pnl_pct` 不可靠。前端对 0 值显示「-」而非误导性数值
3. **持仓详情字段差异**：列表接口含 `current_price`/`pnl_pct`/`source`/`avg_price`/`layers`，但详情接口不含。详情抽屉复用列表缓存数据展示盈亏
4. **信号参数名**：后端使用 `severity_min`（非 `min_severity`）
5. **客户端筛选**：持仓列表后端不支持 tag/symbol 服务端筛选，前端在客户端过滤
6. **平仓接口**：不接受请求体，固定返回 `reason: "manual"`
7. **策略执行响应**：不含动作明细，执行后需刷新持仓/订单列表观察变化
8. **direction 语义区分**：Position/Order 用 `long`/`short`，Signal 用 `bullish`/`bearish`/`neutral`

## 类型检查

```bash
npx tsc --noEmit -p tsconfig.app.json   # 零错误
```
