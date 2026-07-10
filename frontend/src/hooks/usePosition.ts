import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { ENDPOINTS } from '@/lib/constants'
import type { PositionDetail, PositionOrder } from '@/types'

/** 持仓详情 -- GET /api/positions/{id} */
export function usePosition(positionId: string | null) {
  return useQuery<PositionDetail>({
    queryKey: ['position', positionId],
    queryFn: () => apiGet<PositionDetail>(ENDPOINTS.position(positionId!)),
    enabled: !!positionId,
  })
}

/** 持仓订单记录 -- GET /api/positions/{id}/actions */
export function usePositionActions(positionId: string | null) {
  return useQuery<PositionOrder[]>({
    queryKey: ['position-actions', positionId],
    queryFn: () => apiGet<PositionOrder[]>(ENDPOINTS.positionActions(positionId!)),
    enabled: !!positionId,
  })
}
