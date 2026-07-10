import { useState } from 'react'
import { Search } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { DirectionBadge, OrderTypeBadge } from '@/components/ui/DirectionBadges'
import { ErrorState, EmptyState, LoadMoreButton } from '@/components/ui/States'
import { FilterBar, Input, Select } from '@/components/ui/Input'
import { TableSkeleton } from '@/components/ui/Skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { useOrders } from '@/hooks/useOrders'
import { formatDateTime, formatPrice, formatSize } from '@/lib/format'
import type { OrderType } from '@/types'

export function OrdersPage() {
  const [symbol, setSymbol] = useState('')
  const [orderType, setOrderType] = useState<OrderType | ''>('')

  const { data, isLoading, isError, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useOrders({
      symbol: symbol.trim() || undefined,
      orderType: orderType || undefined,
    })

  const orders = data?.pages.flatMap((p) => p.data) ?? []
  const total = data?.pages[0]?.total ?? 0

  return (
    <div>
      <PageHeader title="订单" description={`订单流水记录 · 共 ${total} 条`} />
      <div className="px-6 pb-6">
        {/* 筛选栏 */}
        <FilterBar className="mb-4">
          <div className="relative w-48">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              placeholder="交易对"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="pl-8"
            />
          </div>
          <Select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as OrderType | '')}
            className="w-36"
          >
            <option value="">全部类型</option>
            <option value="OPEN">开仓</option>
            <option value="ADD">加仓</option>
            <option value="REDUCE">减仓</option>
            <option value="CLOSE">平仓</option>
          </Select>
        </FilterBar>

        {/* 表格 */}
        <div className="rounded-lg border border-border">
          {isLoading ? (
            <TableSkeleton rows={10} cols={7} />
          ) : isError ? (
            <ErrorState message={error?.message ?? '加载失败'} onRetry={() => refetch()} />
          ) : orders.length === 0 ? (
            <EmptyState message="暂无订单记录" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>交易对</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>方向</TableHead>
                  <TableHead className="text-right">数量</TableHead>
                  <TableHead className="text-right">价格</TableHead>
                  <TableHead>原因</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(order.created_at)}
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium">
                      {order.symbol}
                    </TableCell>
                    <TableCell>
                      <OrderTypeBadge type={order.order_type} />
                    </TableCell>
                    <TableCell>
                      <DirectionBadge direction={order.direction} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatSize(order.size)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPrice(order.price)}
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-xs text-muted-foreground">
                      {order.reason}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* 加载更多 */}
        {orders.length > 0 && (
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
