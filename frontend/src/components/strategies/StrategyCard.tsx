import type { ReactNode } from 'react'
import { Play } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'

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
 * 策略卡片 -- 展示配置、持仓统计、执行按钮。
 * 通用组件，马丁和微市值共用。
 */
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
  children,
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
  children?: ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle className="text-base font-semibold text-foreground">{title}</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
        <Button
          size="sm"
          onClick={onExecute}
          disabled={isExecuting}
        >
          <Play size={14} />
          {isExecuting ? '执行中...' : '执行策略'}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 持仓统计 */}
        {isLoading ? (
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
        )}

        {/* 配置 */}
        <div className="rounded-md border border-border p-3">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: configItems.length }).map((_, i) => (
                <Skeleton key={i} className="h-4" />
              ))}
            </div>
          ) : (
            configItems.map((item) => (
              <ConfigItem key={item.label} label={item.label} value={item.value} />
            ))
          )}
        </div>

        {children}
      </CardContent>
    </Card>
  )
}
