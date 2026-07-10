import { useState } from 'react'
import { Search, ChevronDown, ChevronRight } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { MarketDirectionBadge } from '@/components/ui/DirectionBadges'
import { Badge } from '@/components/ui/Badge'
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
import { useSignals } from '@/hooks/useSignals'
import { formatDateTime } from '@/lib/format'
import type { Signal } from '@/types'

/** severity 0-5 颜色映射 */
function severityVariant(severity: number): 'muted' | 'warning' | 'destructive' {
  if (severity <= 1) return 'muted'
  if (severity <= 3) return 'warning'
  return 'destructive'
}

/** 信号行，支持展开 metadata */
function SignalRow({ signal }: { signal: Signal }) {
  const [expanded, setExpanded] = useState(false)
  const hasMetadata = Object.keys(signal.metadata).length > 0

  return (
    <>
      <TableRow
        className={hasMetadata ? 'cursor-pointer' : ''}
        onClick={() => hasMetadata && setExpanded((v) => !v)}
      >
        <TableCell className="text-xs text-muted-foreground">
          {formatDateTime(signal.created_at)}
        </TableCell>
        <TableCell className="font-mono text-xs font-medium">{signal.symbol}</TableCell>
        <TableCell className="text-xs">{signal.signal_type}</TableCell>
        <TableCell>
          <MarketDirectionBadge direction={signal.direction} />
        </TableCell>
        <TableCell>
          <Badge variant={severityVariant(signal.severity)}>
            S{signal.severity}
          </Badge>
        </TableCell>
        <TableCell className="max-w-md truncate text-xs text-muted-foreground">
          {signal.description}
        </TableCell>
        <TableCell>
          {hasMetadata ? (
            expanded ? (
              <ChevronDown size={14} className="text-muted-foreground" />
            ) : (
              <ChevronRight size={14} className="text-muted-foreground" />
            )
          ) : null}
        </TableCell>
      </TableRow>
      {expanded && hasMetadata && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={7} className="bg-muted/30">
            <pre className="overflow-x-auto text-xs text-muted-foreground">
              {JSON.stringify(signal.metadata, null, 2)}
            </pre>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

export function SignalsPage() {
  const [symbol, setSymbol] = useState('')
  const [severityMin, setSeverityMin] = useState('')

  const { data, isLoading, isError, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useSignals({
      symbol: symbol.trim() || undefined,
      severityMin: severityMin ? Number(severityMin) : undefined,
    })

  const signals = data?.pages.flatMap((p) => p.data) ?? []
  const total = data?.pages[0]?.total ?? 0

  return (
    <div>
      <PageHeader title="信号" description={`市场信号监控 · 共 ${total} 条`} />
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
            value={severityMin}
            onChange={(e) => setSeverityMin(e.target.value)}
            className="w-40"
          >
            <option value="">全部严重度</option>
            <option value="1">S1 及以上</option>
            <option value="2">S2 及以上</option>
            <option value="3">S3 及以上</option>
            <option value="4">S4 及以上</option>
            <option value="5">仅 S5</option>
          </Select>
        </FilterBar>

        {/* 表格 */}
        <div className="rounded-lg border border-border">
          {isLoading ? (
            <TableSkeleton rows={10} cols={6} />
          ) : isError ? (
            <ErrorState message={error?.message ?? '加载失败'} onRetry={() => refetch()} />
          ) : signals.length === 0 ? (
            <EmptyState message="暂无信号记录" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>交易对</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>方向</TableHead>
                  <TableHead>严重度</TableHead>
                  <TableHead>描述</TableHead>
                  <TableHead className="w-8"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.map((sig) => (
                  <SignalRow key={sig.id} signal={sig} />
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* 加载更多 */}
        {signals.length > 0 && (
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
