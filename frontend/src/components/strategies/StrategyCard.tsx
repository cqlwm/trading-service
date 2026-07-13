import type { ReactNode } from 'react'
import { Clock, Play, Square } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/cn'
import { formatRelative } from '@/lib/format'
import type { StrategySchedule } from '@/types'

/** 调度状态指示器 */
function ScheduleStatus({ schedule }: { schedule: StrategySchedule | null | undefined }) {
  if (!schedule) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="h-2 w-2 rounded-full bg-muted-foreground" />
        未配置调度
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {/* 运行状态灯 */}
      <div className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5">
          {schedule.running && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
          )}
          <span
            className={cn(
              'relative inline-flex h-2.5 w-2.5 rounded-full',
              schedule.running ? 'bg-success' : 'bg-muted-foreground',
            )}
          />
        </span>
        <span className={cn('text-sm font-medium', schedule.running ? 'text-success' : 'text-muted-foreground')}>
          {schedule.running ? '运行中' : '已停止'}
        </span>
      </div>

      {/* cron 表达式 */}
      <Badge variant="outline" className="font-mono text-xs">
        {schedule.cron}
      </Badge>

      {/* 下次执行时间 */}
      {schedule.running && schedule.next_run_at && (
        <span className="text-xs text-muted-foreground">
          下次: {formatRelative(schedule.next_run_at)}
        </span>
      )}

      {/* 上次执行时间 */}
      {schedule.last_run_at && (
        <span className="text-xs text-muted-foreground">
          上次: {formatRelative(schedule.last_run_at)}
        </span>
      )}
    </div>
  )
}

/** 配置项展示 */
function ConfigItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/40 py-1.5 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono font-medium tabular-nums">{value}</span>
    </div>
  )
}

/**
 * 策略行 -- 每个策略占一整行，左侧策略卡片，右侧执行历史。
 * 由 StrategiesPage 组装左右两栏。
 */

/** 策略卡片（左栏） */
export function StrategyCard({
  title,
  description,
  configItems,
  openPositions,
  totalPositions,
  maxPositions,
  isLoading,
  isExecuting,
  onExecute,
  schedule,
  isStarting,
  isStopping,
  onStart,
  onStop,
  showPositions = true,
}: {
  title: string
  description: string
  configItems: { label: string; value: ReactNode }[]
  openPositions: number
  totalPositions: number
  maxPositions: number
  isLoading: boolean
  isExecuting: boolean
  onExecute: () => void
  schedule: StrategySchedule | null | undefined
  isStarting: boolean
  isStopping: boolean
  onStop: () => void
  onStart: () => void
  /** 是否展示持仓统计区块（内容型策略不持仓，设为 false 隐藏）。默认 true。 */
  showPositions?: boolean
}) {
  const running = schedule?.running ?? false

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-shrink-0 flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base font-semibold text-foreground">{title}</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* 启停按钮 */}
          {running ? (
            <Button
              size="sm"
              variant="outline"
              disabled={isStopping}
              onClick={onStop}
            >
              <Square size={14} />
              {isStopping ? '停止中...' : '停止'}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="secondary"
              disabled={isStarting}
              onClick={onStart}
            >
              <Play size={14} />
              {isStarting ? '启动中...' : '启动'}
            </Button>
          )}
          {/* 手动执行 */}
          <Button
            size="sm"
            onClick={onExecute}
            disabled={isExecuting}
          >
            <Clock size={14} />
            {isExecuting ? '执行中...' : '立即执行'}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden">
        {/* 调度状态 */}
        <div className="rounded-md border border-border p-3">
          {isLoading ? (
            <Skeleton className="h-6" />
          ) : (
            <ScheduleStatus schedule={schedule} />
          )}
        </div>

        {/* 持仓统计（内容型策略不持仓，可隐藏） */}
        {showPositions &&
          (isLoading ? (
            <Skeleton className="h-12" />
          ) : (
            <div className="flex items-center gap-4 rounded-md bg-muted/40 p-3">
              <div>
                <div className="text-xs text-muted-foreground">开仓中</div>
                <div className="text-lg font-bold text-success tabular-nums">{openPositions}</div>
              </div>
              <div className="text-muted-foreground/40">/</div>
              <div>
                <div className="text-xs text-muted-foreground">总计</div>
                <div className="text-lg font-bold tabular-nums">{totalPositions}</div>
              </div>
              <div className="ml-auto">
                <Badge variant={openPositions >= maxPositions ? 'warning' : 'muted'}>
                  上限 {maxPositions}
                </Badge>
              </div>
            </div>
          ))}

        {/* 配置 */}
        <div className="flex-1 rounded-md border border-border p-3">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: configItems.length }).map((_, i) => (
                <Skeleton key={i} className="h-4" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-x-6">
              {configItems.map((item) => (
                <ConfigItem key={item.label} label={item.label} value={item.value} />
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
