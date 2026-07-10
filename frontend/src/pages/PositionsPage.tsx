import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'

import { PositionDetailDrawer } from '@/components/positions/PositionDetailDrawer'
import { EmptyPositions, PositionTable } from '@/components/positions/PositionTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { ErrorState, EmptyState } from '@/components/ui/States'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Tabs, type TabItem } from '@/components/ui/Tabs'
import { Input } from '@/components/ui/Input'
import { usePositions } from '@/hooks/usePositions'
import type { PositionStatus } from '@/types'

type FilterStatus = PositionStatus | 'all'

export function PositionsPage() {
  const [status, setStatus] = useState<FilterStatus>('all')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data, isLoading, isError, error, refetch } = usePositions(
    status === 'all' ? 'all' : status,
  )

  // 客户端 tag/symbol 筛选（后端不支持服务端筛选）
  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.trim().toUpperCase()
    if (!q) return data
    return data.filter(
      (p) => p.symbol.toUpperCase().includes(q) || p.tag.toUpperCase().includes(q),
    )
  }, [data, search])

  // tab 计数（基于未筛选的总数据）
  const counts = useMemo(() => {
    const all = data ?? []
    return {
      all: all.length,
      open: all.filter((p) => p.status === 'open').length,
      closed: all.filter((p) => p.status === 'closed').length,
    }
  }, [data])

  const tabItems: TabItem<FilterStatus>[] = [
    { value: 'all', label: '全部', count: counts.all },
    { value: 'open', label: '持仓中', count: counts.open },
    { value: 'closed', label: '已平仓', count: counts.closed },
  ]

  // 选中的持仓列表数据（传给抽屉用于显示盈亏）
  const selectedItem = data?.find((p) => p.id === selectedId)

  return (
    <div>
      <PageHeader title="持仓" description="查看所有持仓（含历史）" />
      <div className="px-6 pb-6">
        <div className="mb-4 flex items-center justify-between gap-4">
          <Tabs items={tabItems} value={status} onChange={setStatus} />
          <div className="relative w-56">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              placeholder="搜索交易对 / 标签"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8"
            />
          </div>
        </div>

        <div className="rounded-lg border border-border">
          {isLoading ? (
            <TableSkeleton rows={8} cols={8} />
          ) : isError ? (
            <ErrorState message={error?.message ?? '加载失败'} onRetry={() => refetch()} />
          ) : filtered.length === 0 ? (
            search ? (
              <EmptyState message={`未找到匹配「${search}」的持仓`} />
            ) : (
              <EmptyPositions />
            )
          ) : (
            <PositionTable positions={filtered} onRowClick={setSelectedId} />
          )}
        </div>
      </div>

      <PositionDetailDrawer
        positionId={selectedId}
        onClose={() => setSelectedId(null)}
        listData={selectedItem}
      />
    </div>
  )
}
