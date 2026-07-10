import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { ENDPOINTS, POLL_INTERVAL } from '@/lib/constants'
import type { PositionListItem, PositionStatus } from '@/types'

/** 持仓列表（含历史），可按状态筛选 */
export function usePositions(status?: PositionStatus | 'all') {
  return useQuery<PositionListItem[]>({
    queryKey: ['positions', status],
    queryFn: () => {
      const param = status && status !== 'all' ? `?status=${status}` : ''
      return apiGet<PositionListItem[]>(`${ENDPOINTS.positions}${param}`)
    },
    refetchInterval: POLL_INTERVAL,
  })
}
