/** 格式化工具 -- 时间、价格、百分比，含后端占位值的容错处理 */

/**
 * 格式化时间，后端返回 ISO 8601 UTC 字符串。
 * 显示为本地时间 + 相对时间。
 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** 相对时间，如「3 分钟前」 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const diff = Date.now() - d.getTime()
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec} 秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  return `${day} 天前`
}

/**
 * 格式化价格。
 * 后端 fetch_prices() 是占位实现会返回 0，对 0 值显示「-」避免误导。
 */
export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return '-'
  if (Number.isNaN(value)) return '-'
  // 小数位自适应：大数少位，小数多位
  if (value >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
  if (value >= 1) return value.toFixed(4)
  return value.toFixed(6)
}

/** 仅判断是否为占位 0 值（用于决定是否显示盈亏） */
export function isPlaceholderPrice(value: number | null | undefined): boolean {
  return value === null || value === undefined || value === 0 || Number.isNaN(value)
}

/**
 * 格式化盈亏百分比。
 * 后端 open 持仓在价格占位时 pnl_pct 可能为 0 或异常，需容错。
 */
export function formatPnl(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

/** 格式化数量 */
export function formatSize(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  if (value >= 1) return value.toFixed(4)
  return value.toFixed(6)
}

/** 格式化金额（USDT） */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

/** 格式化市值（带 M/B 缩写，0 或缺失显示 -） */
export function formatMarketCap(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value <= 0) return '-'
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `$${(value / 1_000).toFixed(2)}K`
  return `$${value.toFixed(2)}`
}
