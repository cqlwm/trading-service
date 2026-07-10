import { AlertTriangle, Clock } from 'lucide-react'

import { Drawer } from '@/components/ui/Drawer'
import { DirectionBadge, OrderTypeBadge, StatusBadge } from '@/components/ui/DirectionBadges'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { useClosePosition } from '@/hooks/useMutations'
import { usePosition } from '@/hooks/usePosition'
import { formatDateTime, formatPrice, formatSize } from '@/lib/format'
import type { PositionListItem } from '@/types'

/** 详情字段行 */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/40 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{children}</span>
    </div>
  )
}

/** 持仓详情抽屉 */
export function PositionDetailDrawer({
  positionId,
  onClose,
  listData,
}: {
  positionId: string | null
  onClose: () => void
  /** 传入列表缓存数据，用于详情页展示盈亏（详情接口无此字段） */
  listData?: PositionListItem
}) {
  const { data: position, isLoading, isError } = usePosition(positionId)
  const closeMutation = useClosePosition()

  const isOpen = position?.status === 'open'
  const canClose = isOpen && !closeMutation.isPending

  return (
    <Drawer
      open={!!positionId}
      onClose={onClose}
      title="持仓详情"
      width="max-w-xl"
    >
      {isLoading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-8" />
          <Skeleton className="h-32" />
          <Skeleton className="h-40" />
        </div>
      ) : isError || !position ? (
        <div className="flex flex-col items-center gap-3 py-20 text-center">
          <AlertTriangle size={32} className="text-destructive" />
          <p className="text-sm text-destructive">加载持仓详情失败</p>
        </div>
      ) : (
        <div className="space-y-6 p-5">
          {/* 基本信息 */}
          <div>
            <div className="mb-3 flex items-center gap-2">
              <span className="font-mono text-lg font-semibold">{position.symbol}</span>
              <DirectionBadge direction={position.direction} />
              <StatusBadge status={position.status} />
            </div>
            <div className="rounded-md border border-border">
              <div className="px-4">
                <Field label="持仓 ID">{position.id}</Field>
                <Field label="开仓价">{formatPrice(position.entry_price)}</Field>
                <Field label="持仓数量">{formatSize(position.total_size)}</Field>
                <Field label="层数">{position.layers}</Field>
                <Field label="止盈触发">{position.tp_hit} 次</Field>
                <Field label="标签">{position.tag}</Field>
                {listData && (
                  <Field label="当前价">{formatPrice(listData.current_price)}</Field>
                )}
                {listData && (
                  <Field label="盈亏">
                    <span
                      className={
                        listData.pnl_pct > 0
                          ? 'text-success'
                          : listData.pnl_pct < 0
                            ? 'text-destructive'
                            : 'text-muted-foreground'
                      }
                    >
                      {listData.pnl_pct > 0 ? '+' : ''}
                      {listData.pnl_pct}%
                    </span>
                  </Field>
                )}
                {position.exit_price !== null && (
                  <Field label="平仓价">{formatPrice(position.exit_price)}</Field>
                )}
                <Field label="开仓时间">{formatDateTime(position.created_at)}</Field>
                {position.closed_at && (
                  <Field label="平仓时间">{formatDateTime(position.closed_at)}</Field>
                )}
              </div>
            </div>
          </div>

          {/* 平仓按钮 */}
          {isOpen && (
            <Button
              variant="destructive"
              className="w-full"
              disabled={!canClose}
              onClick={() => {
                if (positionId) closeMutation.mutate(positionId)
              }}
            >
              {closeMutation.isPending ? '平仓中...' : '手动平仓'}
            </Button>
          )}

          {/* 订单记录 */}
          <div>
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium">
              <Clock size={14} /> 订单记录 ({position.orders.length})
            </h3>
            <div className="space-y-2">
              {position.orders.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  暂无订单记录
                </p>
              ) : (
                position.orders.map((order) => (
                  <div
                    key={order.id}
                    className="rounded-md border border-border/60 p-3 text-sm"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <OrderTypeBadge type={order.order_type} />
                      <DirectionBadge direction={order.direction} />
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(order.created_at)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">
                        数量 <span className="font-mono text-foreground">{formatSize(order.size)}</span>
                      </span>
                      <span className="text-muted-foreground">
                        价格 <span className="font-mono text-foreground">{formatPrice(order.price)}</span>
                      </span>
                    </div>
                    {order.reason && (
                      <p className="mt-1.5 text-xs text-muted-foreground">{order.reason}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  )
}
