import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { ENDPOINTS } from '@/lib/constants'
import type { PaginatedResponse, PositionListItem, PositionStatus } from '@/types'

/** 持仓列表（含历史），可按状态筛选 */
export function usePositions(status?: PositionStatus | 'all') {
  return useQuery<PaginatedResponse<PositionListItem>>({
    queryKey: ['positions', status],
    queryFn: () => {
      const param = status && status !== 'all' ? `?status=${status}` : ''
      return apiGet<PaginatedResponse<PositionListItem>>(
        `${ENDPOINTS.positions}${param}`,
      )
    },
  })
}
