/** API 路径与轮询间隔常量 */

/**
 * 后端 API 基址。
 *
 * 本地开发用相对路径 `/api`，由 Vite dev proxy 转发到 127.0.0.1:8001
 * （见 vite.config.ts）。前端在本地运行、后端在本地时走这条路径。
 *
 * 连接远程服务器时，用户在侧边栏切换 host（见 SettingsProvider），
 * 切换后写入 localStorage 的 `api_host`，本函数读取后返回完整 origin + '/api'。
 */
const REMOTE_HOST_KEY = 'api_host'

/** 本地后端（相对路径，走 Vite proxy） */
const LOCAL_BASE = '/api'

/** 获取当前 API 基址：有远程 host 用远程，否则用本地相对路径 */
export function getApiBase(): string {
  const host = localStorage.getItem(REMOTE_HOST_KEY)
  return host ? `${host}/api` : LOCAL_BASE
}

/** 读取当前远程 host（未设置返回 null） */
export function getApiHost(): string | null {
  return localStorage.getItem(REMOTE_HOST_KEY)
}

/** 设置远程 host（传 null 清除，回到本地模式） */
export function setApiHost(host: string | null): void {
  if (host) {
    localStorage.setItem(REMOTE_HOST_KEY, host)
  } else {
    localStorage.removeItem(REMOTE_HOST_KEY)
  }
}

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
