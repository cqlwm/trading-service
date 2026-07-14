/** API 路径与轮询间隔常量 */

export const API_BASE = '/api'

export const POLL_INTERVAL = 5000 // 5 秒轮询
export const PAGE_SIZE = 50 // 加载更多分页大小
export const REQUEST_TIMEOUT = 30000 // 30s，与后端约定一致

export const ENDPOINTS = {
  positions: '/positions',
  position: (id: string) => `/positions/${id}`,
  positionActions: (id: string) => `/positions/${id}/actions`,
  closePosition: (id: string) => `/positions/${id}/close`,
  orders: '/orders',
  signals: '/signals',
  timeline: '/timeline',
  story: (symbol: string) => `/story/${symbol}`,
  martingaleExecute: '/strategies/martingale/execute',
  martingaleStatus: '/strategies/martingale/status',
  martingaleShortExecute: '/strategies/martingale-short/execute',
  martingaleShortStatus: '/strategies/martingale-short/status',
  microCapExecute: '/strategies/micro-cap/execute',
  microCapStatus: '/strategies/micro-cap/status',
  microCapHistory: '/strategies/micro-cap/history',
  contentScanExecute: '/strategies/content-scan/execute',
  contentScanStatus: '/strategies/content-scan/status',
  // 调度控制
  strategyStart: (name: string) => `/strategies/${name}/start`,
  strategyStop: (name: string) => `/strategies/${name}/stop`,
  strategySchedule: (name: string) => `/strategies/${name}/schedule`,
  strategyExecutions: (name: string) => `/strategies/${name}/executions`,
  executionDetail: (name: string, id: string) => `/strategies/${name}/executions/${id}`,
  // 贴文发布
  publishPost: (id: string) => `/posts/${id}/publish`,
} as const
