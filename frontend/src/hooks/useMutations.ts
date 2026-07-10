import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { apiPost } from '@/api/client'
import { ENDPOINTS } from '@/lib/constants'
import type {
  ClosePositionResponse,
  StrategyExecuteResponse,
} from '@/types'

/** 平仓 -- POST /api/positions/{id}/close */
export function useClosePosition() {
  const qc = useQueryClient()
  return useMutation<ClosePositionResponse, Error, string>({
    mutationFn: (positionId) =>
      apiPost<ClosePositionResponse>(ENDPOINTS.closePosition(positionId)),
    onSuccess: (data) => {
      toast.success(
        `已平仓 ${data.position_id}，平仓价 ${data.close_price}，盈亏 ${data.pnl_pct}%`,
      )
      // 平仓后刷新持仓列表
      qc.invalidateQueries({ queryKey: ['positions'] })
      qc.invalidateQueries({ queryKey: ['position', data.position_id] })
      qc.invalidateQueries({ queryKey: ['orders'] })
    },
    onError: (err) => {
      toast.error(`平仓失败：${err.message}`)
    },
  })
}

/** 执行策略 -- 通用 mutation，支持 martingale / micro-cap */
export function useExecuteStrategy(strategy: 'martingale' | 'micro-cap') {
  const qc = useQueryClient()
  const endpoint =
    strategy === 'martingale'
      ? ENDPOINTS.martingaleExecute
      : ENDPOINTS.microCapExecute

  return useMutation<StrategyExecuteResponse, Error>({
    mutationFn: () => apiPost<StrategyExecuteResponse>(endpoint),
    onSuccess: () => {
      toast.success(`${strategy === 'martingale' ? '马丁' : '微市值'}策略执行完成`)
      // 策略执行后刷新所有相关数据
      qc.invalidateQueries({ queryKey: ['positions'] })
      qc.invalidateQueries({ queryKey: ['orders'] })
      qc.invalidateQueries({ queryKey: ['strategy-status'] })
      qc.invalidateQueries({ queryKey: ['timeline'] })
    },
    onError: (err) => {
      toast.error(`策略执行失败：${err.message}`)
    },
  })
}
