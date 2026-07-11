import { ListOrdered, Megaphone } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { MarketDirectionBadge, OrderTypeBadge } from '@/components/ui/DirectionBadges'
import { ErrorState, EmptyState, LoadMoreButton } from '@/components/ui/States'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { formatDateTime, formatRelative, formatPrice, formatSize } from '@/lib/format'
import { useTimeline } from '@/hooks/useTimeline'
import type { TimelineEvent, TimelineOrderData, TimelineSignalData, TimelineCloseData } from '@/types'
import { cn } from '@/lib/cn'

/** 单条时间线事件 */
function TimelineItem({ event }: { event: TimelineEvent }) {
  const isSignal = event.event_type === 'signal'
  const isOrder = event.event_type === 'order'
  const Icon = isSignal ? Megaphone : ListOrdered

  return (
    <div className="flex gap-3">
      {/* 图标 + 竖线 */}
      <div className="flex flex-col items-center">
        <div
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border',
            isSignal
              ? 'border-warning/30 bg-warning/10 text-warning'
              : 'border-primary/30 bg-primary/10 text-primary',
          )}
        >
          <Icon size={14} />
        </div>
        <div className="w-px flex-1 bg-border" />
      </div>

      {/* 内容 */}
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{formatDateTime(event.timestamp)}</span>
          <span>·</span>
          <span>{formatRelative(event.timestamp)}</span>
        </div>

        {isSignal && <SignalContent data={event.data as TimelineSignalData} />}
        {isOrder && <OrderContent data={event.data as TimelineOrderData} />}
        {event.event_type === 'close' && (
          <CloseContent data={event.data as TimelineCloseData} />
        )}
      </div>
    </div>
  )
}

/** 信号事件内容 */
function SignalContent({ data }: { data: TimelineSignalData }) {
  return (
    <div className="mt-1.5 rounded-md border border-border/60 p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-sm font-medium">{data.symbol}</span>
        <MarketDirectionBadge direction={data.direction} />
        <Badge variant="muted">S{data.severity}</Badge>
        <span className="text-xs text-muted-foreground">{data.signal_type}</span>
      </div>
      <p className="text-sm text-muted-foreground">{data.description}</p>
    </div>
  )
}

/** 订单事件内容 */
function OrderContent({ data }: { data: TimelineOrderData }) {
  return (
    <div className="mt-1.5 rounded-md border border-border/60 p-3">
      <div className="flex items-center gap-2">
        <OrderTypeBadge type={data.order_type} />
        <span className="tabular-nums text-sm">
          {formatSize(data.size)} @ {formatPrice(data.price)}
        </span>
      </div>
    </div>
  )
}

/** 平仓事件内容 */
function CloseContent({ data }: { data: TimelineCloseData }) {
  return (
    <div className="mt-1.5 rounded-md border border-destructive/30 bg-destructive/5 p-3">
      <div className="flex items-center gap-2">
        <Badge variant="destructive">平仓</Badge>
        <span className="tabular-nums text-sm">{formatPrice(data.close_price)}</span>
        <span
          className={cn(
            'tabular-nums text-sm font-medium',
            data.pnl_pct > 0 ? 'text-success' : data.pnl_pct < 0 ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          {data.pnl_pct > 0 ? '+' : ''}
          {data.pnl_pct}%
        </span>
      </div>
    </div>
  )
}

export function TimelinePage() {
  const { data, isLoading, isError, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useTimeline()

  const events = data?.pages.flatMap((p) => p.data) ?? []
  const total = data?.pages[0]?.total ?? 0

  return (
    <div>
      <PageHeader
        title="时间线"
        description={`全局交易事件流（信号 + 订单）· 共 ${total} 条 · 5 秒自动刷新`}
      />
      <div className="px-6 pb-6">
        <div className="rounded-lg border border-border p-4">
          {isLoading ? (
            <TableSkeleton rows={6} cols={1} />
          ) : isError ? (
            <ErrorState message={error?.message ?? '加载失败'} onRetry={() => refetch()} />
          ) : events.length === 0 ? (
            <EmptyState message="暂无事件" />
          ) : (
            <div>
              {events.map((event, i) => (
                <TimelineItem key={`${event.timestamp}-${i}`} event={event} />
              ))}
            </div>
          )}
        </div>

        {events.length > 0 && (
          <LoadMoreButton
            onClick={() => fetchNextPage()}
            disabled={!hasNextPage}
            loading={isFetchingNextPage}
          />
        )}
      </div>
    </div>
  )
}
