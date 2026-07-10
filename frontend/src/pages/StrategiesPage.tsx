import { Activity, History } from 'lucide-react'

import { StrategyCard } from '@/components/strategies/StrategyCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import {
  useExecuteStrategy,
  useStartStrategySchedule,
  useStopStrategySchedule,
} from '@/hooks/useMutations'
import {
  useMartingaleStatus,
  useMartingaleShortStatus,
  useMicroCapStatus,
  useStrategyExecutions,
} from '@/hooks/useStrategies'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/cn'
import type { ReactNode } from 'react'

/** 执行历史面板（右栏） */
function ExecutionHistoryPanel({ name }: { name: string }) {
  const { data: executions, isLoading } = useStrategyExecutions(name, 10)

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-shrink-0">
        <CardTitle>
          <span className="flex items-center gap-1.5">
            <History size={14} /> 执行记录
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-hidden p-0">
          <div className="h-full max-h-72 overflow-y-auto px-4 py-4">
          {isLoading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">加载中...</p>
          ) : (executions ?? []).length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">暂无执行记录</p>
          ) : (
            <div className="space-y-1.5">
              {(executions ?? []).map((exec) => (
                <div
                  key={exec.id}
                  className="flex items-center gap-2 rounded-md border border-border/60 p-1.5 text-sm"
                >
                  <span
                    className={cn(
                      'h-1.5 w-1.5 shrink-0 rounded-full',
                      exec.success ? 'bg-success' : 'bg-destructive',
                    )}
                  />
                  <span className="shrink-0 text-xs text-muted-foreground font-mono">
                    {formatDateTime(exec.started_at)}
                  </span>
                  <Badge variant={exec.success ? 'success' : 'destructive'} className="shrink-0 text-xs">
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
        </div>
      </CardContent>
    </Card>
  )
}

/** 策略行 -- 左侧策略卡片 + 右侧执行历史，整体占一整行 */
function StrategyRow({
  card,
  historyName,
}: {
  card: ReactNode
  historyName: string
}) {
  return (
    <div className="grid items-stretch gap-4 lg:grid-cols-5">
      <div className="lg:col-span-3">{card}</div>
      <div className="lg:col-span-2">
        <ExecutionHistoryPanel name={historyName} />
      </div>
    </div>
  )
}

export function StrategiesPage() {
  const martingale = useMartingaleStatus()
  const martingaleShort = useMartingaleShortStatus()
  const microCap = useMicroCapStatus()
  const executeMartingale = useExecuteStrategy('martingale')
  const executeMartingaleShort = useExecuteStrategy('martingale-short')
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
        {/* 马丁做多 */}
        <StrategyRow
          historyName="martingale"
          card={
            <StrategyCard
              title="马丁格尔"
              description="马丁格尔做多策略 · BTC/ETH 静态选币"
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
                { label: '加仓步长', value: `${martingale.data?.config.safety_order_step_scale ?? 0}x` },
                { label: '加仓倍数', value: `${martingale.data?.config.safety_order_volume_scale ?? 0}x` },
              ]}
            />
          }
        />

        {/* 马丁做空 */}
        <StrategyRow
          historyName="martingale_short"
          card={
            <StrategyCard
              title="马丁做空"
              description="涨幅榜选币 + 技术分析做空信号 + 做空马丁"
              isLoading={martingaleShort.isLoading}
              isExecuting={executeMartingaleShort.isPending}
              onExecute={() => executeMartingaleShort.mutate()}
              schedule={martingaleShort.data?.schedule}
              isStarting={startSchedule.isPending}
              isStopping={stopSchedule.isPending}
              onStart={() => startSchedule.mutate('martingale_short')}
              onStop={() => stopSchedule.mutate('martingale_short')}
              openPositions={martingaleShort.data?.open_positions ?? 0}
              totalPositions={martingaleShort.data?.total_positions ?? 0}
              maxPositions={martingaleShort.data?.config.max_positions ?? 0}
              configItems={[
                { label: '基础订单', value: `$${martingaleShort.data?.config.base_order_size ?? 0}` },
                { label: '安全单数', value: martingaleShort.data?.config.safety_order_count ?? 0 },
                { label: '止盈 (%)', value: `${martingaleShort.data?.config.take_profit_pct ?? 0}%` },
                { label: '止损 (%)', value: `${martingaleShort.data?.config.stop_loss_pct ?? 0}%` },
                { label: '加仓步长', value: `${martingaleShort.data?.config.safety_order_step_scale ?? 0}x` },
                { label: '加仓倍数', value: `${martingaleShort.data?.config.safety_order_volume_scale ?? 0}x` },
              ]}
            />
          }
        />

        {/* 微市值 */}
        <StrategyRow
          historyName="micro_cap"
          card={
            <StrategyCard
              title="微市值"
              description="Alpha 代币选币 + 技术分析做多"
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
                { label: '仓位金额', value: `$${microCap.data?.config.position_size_usdt ?? 0}` },
                { label: '止盈 (%)', value: `${microCap.data?.config.take_profit_pct ?? 0}%` },
                { label: '止损 (%)', value: `${microCap.data?.config.stop_loss_pct ?? 0}%` },
                { label: '最低量', value: `$${(microCap.data?.config.min_volume_usdt ?? 0).toLocaleString()}` },
                { label: '最大市值', value: `$${(microCap.data?.config.max_market_cap ?? 0).toLocaleString()}` },
              ]}
            />
          }
        />
      </div>
    </div>
  )
}
