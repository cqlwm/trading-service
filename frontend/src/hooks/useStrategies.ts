import { useQuery } from '@tanstack/react-query'

import { apiGet } from '@/api/client'
import { ENDPOINTS, POLL_INTERVAL } from '@/lib/constants'
import type {
  ContentScanStatus,
  ExecutionDetail,
  MartingaleStatus,
  MicroCapHistoryItem,
  MicroCapStatus,
  StrategyExecution,
} from '@/types'

/** 马丁策略状态 */
export function useMartingaleStatus() {
  return useQuery<MartingaleStatus>({
    queryKey: ['strategy-status', 'martingale'],
    queryFn: () => apiGet<MartingaleStatus>(ENDPOINTS.martingaleStatus),
    refetchInterval: POLL_INTERVAL,
  })
}

/** 马丁做空策略状态 */
export function useMartingaleShortStatus() {
  return useQuery<MartingaleStatus>({
    queryKey: ['strategy-status', 'martingale-short'],
    queryFn: () => apiGet<MartingaleStatus>(ENDPOINTS.martingaleShortStatus),
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

/** 内容扫描策略状态 */
export function useContentScanStatus() {
  return useQuery<ContentScanStatus>({
    queryKey: ['strategy-status', 'content-scan'],
    queryFn: () => apiGet<ContentScanStatus>(ENDPOINTS.contentScanStatus),
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

/** 策略执行历史 */
export function useStrategyExecutions(name: string, limit = 10) {
  return useQuery<StrategyExecution[]>({
    queryKey: ['strategy-executions', name, limit],
    queryFn: async () => {
      const resp = await apiGet<{ data: StrategyExecution[]; total: number }>(
        `${ENDPOINTS.strategyExecutions(name)}?limit=${limit}`,
      )
      return resp.data
    },
    refetchInterval: POLL_INTERVAL,
  })
}

/** 策略执行详情 -- GET /api/strategies/{name}/executions/{id} */
export function useExecutionDetail(name: string, executionId: string | null) {
  return useQuery<ExecutionDetail>({
    queryKey: ['execution-detail', name, executionId],
    queryFn: () => apiGet<ExecutionDetail>(ENDPOINTS.executionDetail(name, executionId!)),
    enabled: !!executionId,
  })
}
