/**
 * 服务层全局配置
 *
 * 默认调用同源 ``/api``；Vite 开发服务器会把它代理到本机 8000 端口。
 * 只有显式设置 ``VITE_USE_MOCK=true`` 才使用演示数据，避免界面把 Mock 结果
 * 误显示为真实扫描、真实画像或真实设置。
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** 统一处理 JSON、超时和后端 detail 错误，页面不需要重复写 fetch 样板。 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 120_000)
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...init.headers,
      },
    })
    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json') ? await response.json() : await response.text()
    if (!response.ok) {
      const message = typeof payload === 'object' && payload && 'detail' in payload
        ? String(payload.detail)
        : String(payload || `HTTP ${response.status}`)
      throw new ApiError(response.status, message)
    }
    return payload as T
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, '请求超时，请检查本地 FastAPI 服务和运行日志')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function apiDownload(path: string, filename: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(response.status, payload?.detail || `下载失败：HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** 模拟网络延迟 200~600ms */
export function delay<T>(data: T, min = 200, max = 600): Promise<T> {
  const ms = min + Math.floor(Math.random() * (max - min))
  return new Promise((resolve) => setTimeout(() => resolve(data), ms))
}

/** 深拷贝一份数据再返回，避免调用方直接持有 mock 引用 */
export function copy<T>(data: T): T {
  return JSON.parse(JSON.stringify(data)) as T
}
