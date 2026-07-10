import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE } from '@/lib/constants'
import type { PaginatedResponse, Signal } from '@/types'

interface SignalsParams {
  symbol?: string
  severityMin?: number
}

/**
 * 信号监控 -- 加载更多分页。
 * 注意后端参数名为 severity_min（非 min_severity）。
 */
export function useSignals(params: SignalsParams = {}) {
  return useInfiniteQuery<PaginatedResponse<Signal>>({
    queryKey: ['signals', params.symbol, params.severityMin],
    queryFn: ({ pageParam }) =>
      apiGet<PaginatedResponse<Signal>>(
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
      const loaded = allPages.reduce((sum, p) => sum + p.data.length, 0)
      if (loaded >= lastPage.total) return undefined
      return loaded
    },
  })
}

/** 最近 N 条信号（Dashboard 用） */
export function useRecentSignals(limit = 5) {
  return useQuery<Signal[]>({
    queryKey: ['signals-recent', limit],
    queryFn: async () => {
      const resp = await apiGet<PaginatedResponse<Signal>>(
        ENDPOINTS.signals + buildQuery({ limit }),
      )
      return resp.data
    },
  })
}
