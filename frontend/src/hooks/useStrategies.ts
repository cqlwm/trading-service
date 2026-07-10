import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { ENDPOINTS, POLL_INTERVAL } from '@/lib/constants'
import type { MartingaleStatus, MicroCapHistoryItem, MicroCapStatus } from '@/types'

/** 马丁策略状态 */
export function useMartingaleStatus() {
  return useQuery<MartingaleStatus>({
    queryKey: ['strategy-status', 'martingale'],
    queryFn: () => apiGet<MartingaleStatus>(ENDPOINTS.martingaleStatus),
    refetchInterval: POLL_INTERVAL,
  })
}

/** 微市值策略状态 */
export function useMicroCapStatus() {
  return useQuery<MicroCapStatus>({
    queryKey: ['strategy-status', 'micro-cap'],
    queryFn: () => apiGet<MicroCapStatus>(ENDPOINTS.microCapStatus),
    refetchInterval: POLL_INTERVAL,
  })
}

/** 微市值历史记录 */
export function useMicroCapHistory(limit = 20) {
  return useQuery<MicroCapHistoryItem[]>({
    queryKey: ['micro-cap-history', limit],
    queryFn: () =>
      apiGet<MicroCapHistoryItem[]>(
        `${ENDPOINTS.microCapHistory}?limit=${limit}`,
      ),
  })
}
