import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE } from '@/lib/constants'
import type { PaginatedResponse, TimelineEvent } from '@/types'

/**
 * 全局交易时间线 -- 倒序。
 * 事件混合 signal/order/close 三种类型。
 */
export function useTimeline() {
  return useInfiniteQuery<PaginatedResponse<TimelineEvent>>({
    queryKey: ['timeline'],
    queryFn: ({ pageParam }) =>
      apiGet<PaginatedResponse<TimelineEvent>>(
        ENDPOINTS.timeline + buildQuery({ limit: PAGE_SIZE, offset: (pageParam as number) ?? 0 }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, p) => sum + p.data.length, 0)
      if (loaded >= lastPage.total) return undefined
      return loaded
    },
  })
}

/** 单币种交易故事 -- 正序，进入刷新 */
export function useStory(symbol: string | null) {
  return useQuery<TimelineEvent[]>({
    queryKey: ['story', symbol],
    queryFn: () => apiGet<TimelineEvent[]>(ENDPOINTS.story(symbol!)),
    enabled: !!symbol,
  })
}
