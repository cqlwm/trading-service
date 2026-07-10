import { useState } from 'react'
import { Activity, ChevronDown, ChevronRight, History } from 'lucide-react'

import { StrategyCard } from '@/components/strategies/StrategyCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatusBadge } from '@/components/ui/DirectionBadges'
import {
  useExecuteStrategy,
  useStartStrategySchedule,
  useStopStrategySchedule,
} from '@/hooks/useMutations'
import {
  useMartingaleStatus,
  useMicroCapStatus,
  useMicroCapHistory,
  useStrategyExecutions,
} from '@/hooks/useStrategies'
import { formatDateTime, formatPrice } from '@/lib/format'
import { cn } from '@/lib/cn'

/** 执行历史折叠列表 */
function ExecutionHistory({ name }: { name: string }) {
  const [expanded, setExpanded] = useState(false)
  const { data: executions, isLoading } = useStrategyExecutions(name, 10)

  return (
    <Card>
      <CardHeader>
        <button
          className="flex w-full items-center justify-between"
          onClick={() => setExpanded((v) => !v)}
        >
          <CardTitle>
            <span className="flex items-center gap-1.5">
              <History size={14} /> 最近执行记录
            </span>
          </CardTitle>
          {expanded ? (
            <ChevronDown size={16} className="text-muted-foreground" />
          ) : (
            <ChevronRight size={16} className="text-muted-foreground" />
          )}
        </button>
      </CardHeader>
      {expanded && (
        <CardContent>
          {isLoading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">加载中...</p>
          ) : (executions ?? []).length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">暂无执行记录</p>
          ) : (
            <div className="space-y-2">
              {(executions ?? []).map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center gap-3 rounded-md border border-border/60 p-2 text-sm"
                >
                  <span
                    className={cn(
                      'h-2 w-2 shrink-0 rounded-full',
                      exec.success ? 'bg-success' : 'bg-destructive',
                    )}
                  />
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(exec.started_at)}
                  </span>
                  <Badge variant={exec.success ? 'success' : 'destructive'}>
                    {exec.success ? `${exec.action_count} 项操作` : '失败'}
                  </Badge>
                  {exec.actions.length > 0 && (
                    <span className="flex-1 truncate text-xs text-muted-foreground">
                      {exec.actions.map((a) => `${a.symbol} ${a.detail}`).join('; ')}
                    </span>
                  )}
                  {exec.error && (
                    <span className="flex-1 truncate text-xs text-destructive">
                      {exec.error}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

export function StrategiesPage() {
  const martingale = useMartingaleStatus()
  const microCap = useMicroCapStatus()
  const history = useMicroCapHistory(20)
  const executeMartingale = useExecuteStrategy('martingale')
  const executeMicroCap = useExecuteStrategy('micro-cap')
  const startSchedule = useStartStrategySchedule()
  const stopSchedule = useStopStrategySchedule()

  return (
    <div>
      <PageHeader
        title="策略"
        description="策略引擎控制台 - 管理定时调度与手动执行"
        actions={
          <Badge variant="outline" className="gap-1.5">
            <Activity size={12} className="text-success" />
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
            schedule={martingale.data?.schedule}
            isStarting={startSchedule.isPending}
            isStopping={stopSchedule.isPending}
            onStart={() => startSchedule.mutate('martingale')}
            onStop={() => stopSchedule.mutate('martingale')}
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
            schedule={microCap.data?.schedule}
            isStarting={startSchedule.isPending}
            isStopping={stopSchedule.isPending}
            onStart={() => startSchedule.mutate('micro_cap')}
            onStop={() => stopSchedule.mutate('micro_cap')}
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

        {/* 执行历史 */}
        <div className="grid gap-4 lg:grid-cols-2">
          <ExecutionHistory name="martingale" />
          <ExecutionHistory name="micro_cap" />
        </div>

        {/* 微市值历史记录 */}
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>
              <span className="flex items-center gap-1.5">
                <History size={14} /> 微市值持仓历史
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(history.data ?? []).length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">暂无历史记录</p>
            ) : (
              <div className="space-y-2">
                {(history.data ?? []).map((item, i) => (
                  <div
                    key={`${item.symbol}-${i}`}
                    className="flex items-center gap-3 rounded-md border border-border/60 p-2 text-sm"
                  >
                    <span className="font-mono text-xs font-medium">{item.symbol}</span>
                    <span className="tabular-nums text-xs text-muted-foreground">
                      开仓 {formatPrice(item.entry_price)}
                    </span>
                    {item.exit_price && (
                      <span className="tabular-nums text-xs text-muted-foreground">
                        平仓 {formatPrice(item.exit_price)}
                      </span>
                    )}
                    <StatusBadge status={item.status} />
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatDateTime(item.created_at)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
