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
  microCapExecute: '/strategies/micro-cap/execute',
  microCapStatus: '/strategies/micro-cap/status',
  microCapHistory: '/strategies/micro-cap/history',
} as const
