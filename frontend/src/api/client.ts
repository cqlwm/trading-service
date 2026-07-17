import { getApiBase, REQUEST_TIMEOUT } from '@/lib/constants'

/** 统一 API 错误，归一化后端 {detail: string} 格式 */
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface FetchOptions extends RequestInit {
  timeout?: number
}

/** 底层 fetch 封装：超时控制 + 错误归一化 */
async function request<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { timeout = REQUEST_TIMEOUT, ...init } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  try {
    const resp = await fetch(`${getApiBase()}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...init.headers,
      },
    })

    if (!resp.ok) {
      let message = `请求失败 (${resp.status})`
      try {
        const body = await resp.json()
        // 后端错误格式：{detail: string} 或 {detail: [{msg: string}]}
        if (typeof body.detail === 'string') {
          message = body.detail
        } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
          message = body.detail[0].msg
        }
      } catch {
        // 非 JSON 响应，使用默认 message
      }
      throw new ApiError(resp.status, message)
    }

    // 204 或空响应
    if (resp.status === 204) return undefined as T
    return (await resp.json()) as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiError(0, '请求超时，请检查后端服务是否运行')
    }
    throw new ApiError(0, '网络错误，无法连接到服务器')
  } finally {
    clearTimeout(timer)
  }
}

/** 构造查询字符串，跳过 undefined/null/空字符串 */
export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  )
  if (entries.length === 0) return ''
  const sp = new URLSearchParams()
  for (const [k, v] of entries) sp.set(k, String(v))
  return `?${sp.toString()}`
}

export const apiGet = <T>(path: string): Promise<T> => request<T>(path, { method: 'GET' })
export const apiPost = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, {
    method: 'POST',
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
