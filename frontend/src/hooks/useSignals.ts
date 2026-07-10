import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE } from '@/lib/constants'
import type { Signal } from '@/types'

interface SignalsParams {
  symbol?: string
  severityMin?: number
}

/**
 * 信号监控 -- 加载更多分页。
 * 注意后端参数名为 severity_min（非 min_severity）。
 */
export function useSignals(params: SignalsParams = {}) {
  return useInfiniteQuery<Signal[]>({
    queryKey: ['signals', params.symbol, params.severityMin],
    queryFn: ({ pageParam }) =>
      apiGet<Signal[]>(
        ENDPOINTS.signals +
          buildQuery({
            symbol: params.symbol,
            severity_min: params.severityMin,
            limit: PAGE_SIZE,
            offset: (pageParam as number) ?? 0,
          }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) return undefined
      return allPages.length * PAGE_SIZE
    },
  })
}

/** 最近 N 条信号（Dashboard 用） */
export function useRecentSignals(limit = 5) {
  return useInfiniteQuery<Signal[]>({
    queryKey: ['signals-recent', limit],
    queryFn: ({ pageParam }) =>
      apiGet<Signal[]>(
        ENDPOINTS.signals + buildQuery({ limit, offset: (pageParam as number) ?? 0 }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.length < limit ? undefined : limit,
  })
}
