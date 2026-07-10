import { cn } from '@/lib/cn'
import { formatPnl, isPlaceholderPrice } from '@/lib/format'

/**
 * 盈亏徽标。
 * 后端 fetch_prices() 占位返回 0，导致 open 持仓 pnl_pct 不可靠，
 * 当 current_price 为 0 时显示「-」而非误导性数值。
 */
export function PnLBadge({
  pnlPct,
  priceUnavailable = false,
}: {
  pnlPct: number
  priceUnavailable?: boolean
}) {
  const unavailable = priceUnavailable || (pnlPct === 0 && priceUnavailable)
  if (unavailable) {
    return <span className="text-muted-foreground">-</span>
  }

  const positive = pnlPct > 0
  const zero = pnlPct === 0
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium tabular-nums',
        zero
          ? 'bg-muted text-muted-foreground'
          : positive
            ? 'bg-success/15 text-success'
            : 'bg-destructive/15 text-destructive',
      )}
    >
      {formatPnl(pnlPct)}
    </span>
  )
}

/**
 * 价格显示，容错 0 值。
 * 后端 fetch_prices() 返回 0 时显示「-」。
 */
export function PriceDisplay({
  value,
  placeholder = false,
}: {
  value: number | null | undefined
  placeholder?: boolean
}) {
  if (isPlaceholderPrice(value) || placeholder) {
    return <span className="text-muted-foreground">-</span>
  }
  return <span className="tabular-nums">{value!.toLocaleString('en-US', { maximumFractionDigits: 6 })}</span>
}
