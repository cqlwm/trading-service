import { useInfiniteQuery, useQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE, POLL_INTERVAL } from '@/lib/constants'
import type { TimelineEvent } from '@/types'

/**
 * 全局交易时间线 -- 倒序，5 秒轮询。
 * 事件混合 signal/order/close 三种类型。
 */
export function useTimeline() {
  return useInfiniteQuery<TimelineEvent[]>({
    queryKey: ['timeline'],
    queryFn: ({ pageParam }) =>
      apiGet<TimelineEvent[]>(
        ENDPOINTS.timeline + buildQuery({ limit: PAGE_SIZE, offset: (pageParam as number) ?? 0 }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) return undefined
      return allPages.length * PAGE_SIZE
    },
    refetchInterval: POLL_INTERVAL,
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
