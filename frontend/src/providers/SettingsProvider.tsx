import { type ReactNode, createContext, useContext, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { getApiHost, setApiHost } from '@/lib/constants'

/**
 * 后端连接设置。
 *
 * 前端在本地运行，后端可在本地（开发）或远程服务器（生产）。
 * 用户在侧边栏切换，host 写入 localStorage，client.ts 每次请求读取最新值。
 */

/** 服务器后端地址 */
export const SERVER_HOST = 'http://43.108.38.130:8001'

/** 可选的目标：本地（走 Vite proxy）/ 服务器 */
export type ApiTarget = 'local' | 'server'

interface SettingsValue {
  /** 当前目标；host 为 null 即本地 */
  target: ApiTarget
  /** 当前 host（本地模式为 null） */
  host: string | null
  /** 切换目标 */
  switchTarget: (target: ApiTarget) => void
}

const SettingsContext = createContext<SettingsValue | null>(null)

export function SettingsProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [host, setHost] = useState<string | null>(() => getApiHost())

  const value = useMemo<SettingsValue>(() => {
    const switchTarget = (target: ApiTarget) => {
      const nextHost = target === 'server' ? SERVER_HOST : null
      setApiHost(nextHost)
      setHost(nextHost)
      // host 变化后，已缓存的数据失效，重新按新 host 拉取
      queryClient.invalidateQueries()
    }

    return {
      target: host ? 'server' : 'local',
      host,
      switchTarget,
    }
  }, [host, queryClient])

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings(): SettingsValue {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings 必须在 SettingsProvider 内使用')
  return ctx
}
