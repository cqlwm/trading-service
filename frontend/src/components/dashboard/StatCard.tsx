import type { ReactNode } from 'react'

import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/cn'

/** 统计卡片 */
export function StatCard({
  label,
  value,
  icon,
  accent = 'default',
  sub,
}: {
  label: string
  value: string | number
  icon?: ReactNode
  accent?: 'default' | 'success' | 'warning' | 'destructive'
  sub?: string
}) {
  const accentColor = {
    default: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
    destructive: 'text-destructive',
  }[accent]

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        {icon && <span className={cn('opacity-80', accentColor)}>{icon}</span>}
      </div>
      <div className={cn('mt-2 text-2xl font-bold tabular-nums', accentColor)}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  )
}
