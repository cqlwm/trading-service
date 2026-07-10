/**
 * 类型定义层 —— 镜像后端 trading_service/types.py 枚举与领域模型。
 * 所有类型与后端实际实现对齐（以 api/ 下实际返回为准，非架构文档）。
 */

/* ==================== 枚举（对应后端 types.py） ==================== */

/** 交易方向 —— Position/Order 用（对应 TradeDirection） */
export type TradeDirection = 'long' | 'short'

/** 订单类型 —— 对应 OrderType */
export type OrderType = 'OPEN' | 'ADD' | 'REDUCE' | 'CLOSE'

/** 市场方向 —— Signal.direction 用（对应 MarketDirection，语义与 TradeDirection 不同） */
export type MarketDirection = 'bullish' | 'bearish' | 'neutral'

/** 均线穿越信号 —— 对应 CrossSignalType */
export type CrossSignalType = 'golden' | 'dead' | 'near'

/** 持仓状态 */
export type PositionStatus = 'open' | 'closed'

/** 持仓来源（后端由 tag 派生） */
export type PositionSource = 'martingale' | 'micro_cap' | 'short_sell' | 'technical'

/* ==================== 领域模型 ==================== */

/** 订单 —— 对应 GET /api/orders 列表项 */
export interface Order {
  id: string
  position_id: string
  symbol: string
  direction: TradeDirection
  size: number
  price: number
  reason: string
  order_type: OrderType
  created_at: string
}

/** 持仓列表项 —— GET /api/positions 返回（含计算字段） */
export interface PositionListItem {
  id: string
  symbol: string
  direction: TradeDirection
  entry_price: number
  avg_price: number
  current_price: number
  total_size: number
  status: PositionStatus
  exit_price: number | null
  tag: string
  source: PositionSource
  layers: number
  tp_hit: number
  pnl_pct: number
  created_at: string
  closed_at: string | null
}

/** 持仓详情中的订单（字段比列表 Order 少 position_id） —— GET /api/positions/{id} 内嵌 */
export interface PositionOrder {
  id: string
  order_type: OrderType
  size: number
  price: number
  reason: string
  direction: TradeDirection
  created_at: string
}

/** 持仓详情 —— GET /api/positions/{id} 返回（不含 current_price/pnl_pct/source/avg_price/layers） */
export interface PositionDetail {
  id: string
  symbol: string
  direction: TradeDirection
  entry_price: number
  total_size: number
  status: PositionStatus
  exit_price: number | null
  tag: string
  tp_hit: number
  layers: number
  created_at: string
  closed_at: string | null
  orders: PositionOrder[]
}

/** 平仓响应 —— POST /api/positions/{id}/close */
export interface ClosePositionResponse {
  message: string
  position_id: string
  close_price: number
  pnl_pct: number
  reason: string
}

/** 信号 —— GET /api/signals 列表项 */
export interface Signal {
  id: string
  symbol: string
  signal_type: string
  direction: MarketDirection
  severity: number
  description: string
  metadata: Record<string, unknown>
  created_at: string
}

/* ==================== 时间线 ==================== */

/** 时间线事件 data 联合类型 */
export interface TimelineSignalData {
  id: string
  symbol: string
  signal_type: string
  direction: MarketDirection
  severity: number
  description: string
  metadata: Record<string, unknown>
}

export interface TimelineOrderData {
  id: string
  order_type: OrderType
  size: number
  price: number
  reason: string
}

export interface TimelineCloseData {
  position_id: string
  close_price: number
  pnl_pct: number
  reason: string
}

/** 时间线事件 —— GET /api/timeline 或 GET /api/story/{symbol} */
export interface TimelineEvent {
  timestamp: string
  event_type: 'signal' | 'order' | 'close'
  data: TimelineSignalData | TimelineOrderData | TimelineCloseData
}

/* ==================== 策略 ==================== */

/** 策略调度状态 */
export interface StrategySchedule {
  strategy_name: string
  running: boolean
  cron: string
  next_run_at: string | null
  last_run_at: string | null
}

/** 策略执行历史记录 */
export interface StrategyExecution {
  id: string
  strategy_name: string
  started_at: string
  finished_at: string | null
  success: boolean
  action_count: number
  actions: StrategyAction[]
  error: string | null
}

/** 马丁策略状态 -- GET /api/strategies/martingale/status */
export interface MartingaleStatus {
  config: {
    max_positions: number
    base_order_size: number
    safety_order_count: number
    safety_order_step_scale: number
    safety_order_volume_scale: number
    take_profit_pct: number
    stop_loss_pct: number
  }
  open_positions: number
  total_positions: number
  schedule: StrategySchedule | null
}

/** 微市值策略状态 -- GET /api/strategies/micro-cap/status */
export interface MicroCapStatus {
  config: {
    max_positions: number
    position_size_usdt: number
    take_profit_pct: number
    stop_loss_pct: number
    min_volume_usdt: number
    max_market_cap: number
  }
  open_positions: number
  total_positions: number
  schedule: StrategySchedule | null
}

/** 策略执行动作 */
export interface StrategyAction {
  type: string // "open" | "add" | "close" | "skip"
  symbol: string
  detail: string
}

/** 策略执行响应 */
export interface StrategyExecuteResponse {
  status: string
  strategy: string
  actions: StrategyAction[]
  action_count: number
}

/** 微市值历史记录 —— GET /api/strategies/micro-cap/history */
export interface MicroCapHistoryItem {
  symbol: string
  entry_price: number
  exit_price: number | null
  status: PositionStatus
  pnl_pct: number
  created_at: string
}

/* ==================== 查询参数 ==================== */

export interface OrdersQuery {
  symbol?: string
  order_type?: OrderType
  limit?: number
  offset?: number
}

export interface SignalsQuery {
  symbol?: string
  severity_min?: number
  limit?: number
  offset?: number
}

/* ==================== 分页响应 ==================== */

/** 统一分页响应 -- 列表端点返回 {data, total} */
export interface PaginatedResponse<T> {
  data: T[]
  total: number
}
