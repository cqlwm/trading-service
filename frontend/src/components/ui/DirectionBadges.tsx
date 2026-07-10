import { Badge } from '@/components/ui/Badge'
import type { TradeDirection, MarketDirection, OrderType } from '@/types'

/** 多空方向徽标：long 绿、short 红 */
export function DirectionBadge({ direction }: { direction: TradeDirection }) {
  return (
    <Badge variant={direction === 'long' ? 'success' : 'destructive'}>
      {direction === 'long' ? '多' : '空'}
    </Badge>
  )
}

/** 市场方向徽标：bullish 绿、bearish 红、neutral 灰 */
export function MarketDirectionBadge({ direction }: { direction: MarketDirection }) {
  const variant =
    direction === 'bullish' ? 'success' : direction === 'bearish' ? 'destructive' : 'muted'
  const label = direction === 'bullish' ? '看涨' : direction === 'bearish' ? '看跌' : '中性'
  return <Badge variant={variant}>{label}</Badge>
}

/** 订单类型徽标 */
export function OrderTypeBadge({ type }: { type: OrderType }) {
  const config: Record<OrderType, { variant: 'default' | 'success' | 'warning' | 'destructive'; label: string }> = {
    OPEN: { variant: 'default', label: '开仓' },
    ADD: { variant: 'success', label: '加仓' },
    REDUCE: { variant: 'warning', label: '减仓' },
    CLOSE: { variant: 'destructive', label: '平仓' },
  }
  const { variant, label } = config[type]
  return <Badge variant={variant}>{label}</Badge>
}

/** 持仓状态徽标 */
export function StatusBadge({ status }: { status: 'open' | 'closed' }) {
  return (
    <Badge variant={status === 'open' ? 'success' : 'muted'}>
      {status === 'open' ? '持仓中' : '已平仓'}
    </Badge>
  )
}
