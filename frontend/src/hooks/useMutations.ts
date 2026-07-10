import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { apiPost } from '@/api/client'
import { ENDPOINTS } from '@/lib/constants'
import type {
  ClosePositionResponse,
  StrategyExecuteResponse,
  StrategySchedule,
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

/** 执行策略 -- 通用 mutation，支持 martingale / micro-cap / martingale-short */
export function useExecuteStrategy(strategy: 'martingale' | 'micro-cap' | 'martingale-short') {
  const qc = useQueryClient()
  const endpoint =
    strategy === 'martingale'
      ? ENDPOINTS.martingaleExecute
      : strategy === 'martingale-short'
        ? ENDPOINTS.martingaleShortExecute
        : ENDPOINTS.microCapExecute
  const label =
    strategy === 'martingale' ? '马丁' : strategy === 'martingale-short' ? '马丁做空' : '微市值'

  return useMutation<StrategyExecuteResponse, Error>({
    mutationFn: () => apiPost<StrategyExecuteResponse>(endpoint),
    onSuccess: (data) => {
      // 根据执行的动作数量给出不同反馈
      if (data.action_count === 0) {
        toast.info(`${label}策略执行完成，本轮无操作`)
      } else {
        const summary = data.actions
          .map((a) => `${a.symbol} ${a.detail}`)
          .join('\n')
        toast.success(`${label}策略执行完成，共 ${data.action_count} 项操作：\n${summary}`, {
          duration: 6000,
        })
      }
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

/** 启动策略调度 -- POST /api/strategies/{name}/start */
export function useStartStrategySchedule() {
  const qc = useQueryClient()
  return useMutation<StrategySchedule, Error, string>({
    mutationFn: (name) => apiPost<StrategySchedule>(ENDPOINTS.strategyStart(name)),
    onSuccess: (data) => {
      toast.success(`${data.strategy_name} 定时调度已启动`)
      qc.invalidateQueries({ queryKey: ['strategy-status'] })
    },
    onError: (err) => {
      toast.error(`启动调度失败：${err.message}`)
    },
  })
}

/** 停止策略调度 -- POST /api/strategies/{name}/stop */
export function useStopStrategySchedule() {
  const qc = useQueryClient()
  return useMutation<StrategySchedule, Error, string>({
    mutationFn: (name) => apiPost<StrategySchedule>(ENDPOINTS.strategyStop(name)),
    onSuccess: (data) => {
      toast.success(`${data.strategy_name} 定时调度已停止`)
      qc.invalidateQueries({ queryKey: ['strategy-status'] })
    },
    onError: (err) => {
      toast.error(`停止调度失败：${err.message}`)
    },
  })
}
