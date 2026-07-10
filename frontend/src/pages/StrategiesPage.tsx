import { Activity, History } from 'lucide-react'

import { StrategyCard } from '@/components/strategies/StrategyCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/DirectionBadges'
import { PnLBadge } from '@/components/ui/PnLBadge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { useExecuteStrategy } from '@/hooks/useMutations'
import {
  useMartingaleStatus,
  useMicroCapStatus,
  useMicroCapHistory,
} from '@/hooks/useStrategies'
import { formatDateTime, formatPrice } from '@/lib/format'

export function StrategiesPage() {
  const martingale = useMartingaleStatus()
  const microCap = useMicroCapStatus()
  const history = useMicroCapHistory(20)
  const executeMartingale = useExecuteStrategy('martingale')
  const executeMicroCap = useExecuteStrategy('micro-cap')

  return (
    <div>
      <PageHeader
        title="策略"
        description="策略引擎控制台"
        actions={
          <Badge variant="outline" className="gap-1.5">
            <Activity size={12} className="animate-pulse text-success" />
            实时状态
          </Badge>
        }
      />
      <div className="space-y-6 px-6 pb-6">
        <div className="grid gap-4 lg:grid-cols-2">
          {/* 马丁策略 */}
          <StrategyCard
            title="马丁格尔"
            description="马丁格尔加仓策略"
            isLoading={martingale.isLoading}
            isExecuting={executeMartingale.isPending}
            onExecute={() => executeMartingale.mutate()}
            openPositions={martingale.data?.open_positions ?? 0}
            totalPositions={martingale.data?.total_positions ?? 0}
            maxPositions={martingale.data?.config.max_positions ?? 0}
            configItems={[
              { label: '基础订单', value: `$${martingale.data?.config.base_order_size ?? 0}` },
              { label: '安全单数', value: martingale.data?.config.safety_order_count ?? 0 },
              { label: '止盈 (%)', value: `${martingale.data?.config.take_profit_pct ?? 0}%` },
              { label: '止损 (%)', value: `${martingale.data?.config.stop_loss_pct ?? 0}%` },
              {
                label: '加仓步长',
                value: `${martingale.data?.config.safety_order_step_scale ?? 0}x`,
              },
              {
                label: '加仓倍数',
                value: `${martingale.data?.config.safety_order_volume_scale ?? 0}x`,
              },
            ]}
          />

          {/* 微市值策略 */}
          <StrategyCard
            title="微市值"
            description="微市值做多策略"
            isLoading={microCap.isLoading}
            isExecuting={executeMicroCap.isPending}
            onExecute={() => executeMicroCap.mutate()}
            openPositions={microCap.data?.open_positions ?? 0}
            totalPositions={microCap.data?.total_positions ?? 0}
            maxPositions={microCap.data?.config.max_positions ?? 0}
            configItems={[
              {
                label: '仓位金额',
                value: `$${microCap.data?.config.position_size_usdt ?? 0}`,
              },
              { label: '止盈 (%)', value: `${microCap.data?.config.take_profit_pct ?? 0}%` },
              { label: '止损 (%)', value: `${microCap.data?.config.stop_loss_pct ?? 0}%` },
              {
                label: '最低量',
                value: `$${(microCap.data?.config.min_volume_usdt ?? 0).toLocaleString()}`,
              },
              {
                label: '最大市值',
                value: `$${(microCap.data?.config.max_market_cap ?? 0).toLocaleString()}`,
              },
            ]}
          />
        </div>

        {/* 微市值历史记录 */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <History size={14} /> 微市值历史记录
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history.isLoading ? (
              <TableSkeleton rows={5} cols={5} />
            ) : history.isError ? (
              <ErrorState
                message={history.error?.message ?? '加载失败'}
                onRetry={() => history.refetch()}
              />
            ) : (history.data ?? []).length === 0 ? (
              <EmptyState message="暂无历史记录" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>交易对</TableHead>
                    <TableHead className="text-right">开仓价</TableHead>
                    <TableHead className="text-right">平仓价</TableHead>
                    <TableHead className="text-right">盈亏</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(history.data ?? []).map((item, i) => (
                    <TableRow key={`${item.symbol}-${i}`}>
                      <TableCell className="font-mono text-xs font-medium">
                        {item.symbol}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatPrice(item.entry_price)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatPrice(item.exit_price)}
                      </TableCell>
                      <TableCell className="text-right">
                        <PnLBadge pnlPct={item.pnl_pct} />
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={item.status} />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(item.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
