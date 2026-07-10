import { TrendingUp } from 'lucide-react'

import { DirectionBadge, StatusBadge } from '@/components/ui/DirectionBadges'
import { PnLBadge, PriceDisplay } from '@/components/ui/PnLBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { formatDateTime, formatPrice, formatSize } from '@/lib/format'
import { isPlaceholderPrice } from '@/lib/format'
import type { PositionListItem } from '@/types'

/** 持仓列表表格 */
export function PositionTable({
  positions,
  onRowClick,
}: {
  positions: PositionListItem[]
  onRowClick: (id: string) => void
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>交易对</TableHead>
          <TableHead>方向</TableHead>
          <TableHead className="text-right">开仓价</TableHead>
          <TableHead className="text-right">当前价</TableHead>
          <TableHead className="text-right">数量</TableHead>
          <TableHead className="text-center">层数</TableHead>
          <TableHead className="text-center">止盈</TableHead>
          <TableHead className="text-right">盈亏</TableHead>
          <TableHead>来源</TableHead>
          <TableHead>状态</TableHead>
          <TableHead>开仓时间</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {positions.map((p) => {
          const priceUnavailable = isPlaceholderPrice(p.current_price) && p.status === 'open'
          return (
            <TableRow
              key={p.id}
              onClick={() => onRowClick(p.id)}
              className="cursor-pointer"
            >
              <TableCell className="font-mono text-xs font-medium">{p.symbol}</TableCell>
              <TableCell>
                <DirectionBadge direction={p.direction} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatPrice(p.entry_price)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                <PriceDisplay value={p.current_price} placeholder={priceUnavailable} />
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatSize(p.total_size)}
              </TableCell>
              <TableCell className="text-center tabular-nums">{p.layers}</TableCell>
              <TableCell className="text-center tabular-nums">{p.tp_hit}</TableCell>
              <TableCell className="text-right">
                <PnLBadge pnlPct={p.pnl_pct} priceUnavailable={priceUnavailable} />
              </TableCell>
              <TableCell>
                <span className="text-xs text-muted-foreground">{p.source}</span>
              </TableCell>
              <TableCell>
                <StatusBadge status={p.status} />
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatDateTime(p.created_at)}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

/** 空持仓占位 */
export function EmptyPositions() {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      <TrendingUp size={32} className="text-muted-foreground/40" />
      <p className="text-sm text-muted-foreground">暂无持仓记录</p>
    </div>
  )
}
