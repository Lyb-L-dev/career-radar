import { apiRequest, delay, copy, USE_MOCK } from './config'
import { runs } from '@/mocks/runs'
import type { Run } from '@/types'

export async function getRuns(): Promise<Run[]> {
  if (!USE_MOCK) return apiRequest('/runs')
  return delay(copy(runs))
}

export async function getRun(id: string): Promise<Run | undefined> {
  if (!USE_MOCK) return apiRequest(`/runs/${encodeURIComponent(id)}`)
  return delay(copy(runs.find((r) => r.id === id)))
}

export async function createRun(options: { scope: 'all' | 'failed' | 'company' | 'company_type'; companyId?: string; companyType?: import('@/types').CompanyType; sendEmail: boolean }): Promise<{ ok: boolean; runId: string }> {
  if (!USE_MOCK) {
    return apiRequest('/runs', { method: 'POST', body: JSON.stringify(options) })
  }
  return delay({ ok: true, runId: `run-${Date.now()}` }, 300, 500)
}

export async function stopRun(id: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest(`/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' })
  return delay({ ok: true }, 200, 400)
}

export async function retryFailed(id: string): Promise<{ ok: boolean; runId?: string }> {
  if (!USE_MOCK) return apiRequest(`/runs/${encodeURIComponent(id)}/retry`, { method: 'POST' })
  return delay({ ok: true }, 300, 500)
}
