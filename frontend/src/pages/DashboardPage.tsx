import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, ListOrdered, Megaphone, TrendingUp } from 'lucide-react'

import { apiGet } from '@/api/client'
import { StatCard } from '@/components/dashboard/StatCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { MarketDirectionBadge } from '@/components/ui/DirectionBadges'
import { Skeleton } from '@/components/ui/Skeleton'
import { ENDPOINTS } from '@/lib/constants'
import { formatDateTime, formatRelative } from '@/lib/format'
import { useMartingaleStatus, useMicroCapStatus } from '@/hooks/useStrategies'
import { usePositions } from '@/hooks/usePositions'
import { useRecentSignals } from '@/hooks/useSignals'
import type { Order, Signal } from '@/types'

export function DashboardPage() {
  const positions = usePositions('all')
  const martingale = useMartingaleStatus()
  const microCap = useMicroCapStatus()
  const recentSignals = useRecentSignals(5)

  // 最近订单（单独查询，limit=5）
  const recentOrders = useQuery<Order[]>({
    queryKey: ['orders-recent', 5],
    queryFn: () => apiGet<Order[]>(`${ENDPOINTS.orders}?limit=5`),
  })

  const allPositions = positions.data ?? []
  const openCount = allPositions.filter((p) => p.status === 'open').length
  const closedCount = allPositions.filter((p) => p.status === 'closed').length

  return (
    <div>
      <PageHeader title="仪表盘" description="交易服务总览" />
      <div className="space-y-6 px-6 pb-6">
        {/* 统计卡片 */}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="持仓中"
            value={positions.isLoading ? '...' : openCount}
            icon={<TrendingUp size={18} />}
            accent="success"
            sub={`共 ${allPositions.length} 个持仓`}
          />
          <StatCard
            label="已平仓"
            value={positions.isLoading ? '...' : closedCount}
            icon={<Activity size={18} />}
            accent="default"
          />
          <StatCard
            label="马丁策略"
            value={
              martingale.isLoading
                ? '...'
                : `${martingale.data?.open_positions ?? 0} / ${martingale.data?.total_positions ?? 0}`
            }
            icon={<Activity size={18} />}
            sub="开仓 / 总计"
          />
          <StatCard
            label="微市值策略"
            value={
              microCap.isLoading
                ? '...'
                : `${microCap.data?.open_positions ?? 0} / ${microCap.data?.total_positions ?? 0}`
            }
            icon={<Activity size={18} />}
            sub="开仓 / 总计"
          />
        </div>

        {/* 最近信号 + 最近订单 */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* 最近信号 */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>
                <span className="flex items-center gap-1.5">
                  <Megaphone size={14} /> 最近信号
                </span>
              </CardTitle>
              <Link to="/signals" className="text-xs text-primary hover:underline">
                查看全部
              </Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {recentSignals.isLoading ? (
                <Skeleton className="h-20" />
              ) : (recentSignals.data?.pages[0] ?? []).length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">暂无信号</p>
              ) : (
                (recentSignals.data?.pages[0] ?? []).map((sig: Signal) => (
                  <div
                    key={sig.id}
                    className="flex items-center gap-3 rounded-md border border-border/60 p-2 text-sm"
                  >
                    <MarketDirectionBadge direction={sig.direction} />
                    <span className="font-mono text-xs">{sig.symbol}</span>
                    <span className="flex-1 truncate text-muted-foreground">
                      {sig.description}
                    </span>
                    <Badge variant="muted">S{sig.severity}</Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatRelative(sig.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* 最近订单 */}
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>
                <span className="flex items-center gap-1.5">
                  <ListOrdered size={14} /> 最近订单
                </span>
              </CardTitle>
              <Link to="/orders" className="text-xs text-primary hover:underline">
                查看全部
              </Link>
            </CardHeader>
            <CardContent className="space-y-2">
              {recentOrders.isLoading ? (
                <Skeleton className="h-20" />
              ) : (recentOrders.data ?? []).length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">暂无订单</p>
              ) : (
                (recentOrders.data ?? []).map((order) => (
                  <div
                    key={order.id}
                    className="flex items-center gap-3 rounded-md border border-border/60 p-2 text-sm"
                  >
                    <Badge variant="outline">{order.order_type}</Badge>
                    <span className="font-mono text-xs">{order.symbol}</span>
                    <span className="flex-1 truncate text-muted-foreground">
                      {order.reason}
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {order.size} @ {order.price}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(order.created_at)}
                    </span>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
