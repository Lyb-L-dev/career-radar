import { apiRequest } from './config'
import type { ReputationHealth, ReputationScan } from '@/types'

export function getReputationHealth(): Promise<ReputationHealth> {
  return apiRequest<ReputationHealth>('/reputation/health')
}

export function getJobReputation(jobId: string): Promise<ReputationScan | null> {
  return apiRequest<ReputationScan | null>(`/jobs/${encodeURIComponent(jobId)}/reputation`)
}

export function getReputationScan(scanId: string): Promise<ReputationScan> {
  return apiRequest<ReputationScan>(`/reputation-scans/${encodeURIComponent(scanId)}`)
}

export function startReputationScan(jobId: string): Promise<{ ok: boolean; scanId: string }> {
  return apiRequest(`/jobs/${encodeURIComponent(jobId)}/reputation-scan`, { method: 'POST' })
}
