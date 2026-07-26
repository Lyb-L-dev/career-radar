import { ApiError, apiDownload, apiRequest, delay, USE_MOCK } from './config'
import type { ApplicationProfileStatus, ApplicationTask } from '@/types'

type AcceptedAction = { ok: boolean; applicationId: string }

export async function getApplicationProfileStatus(): Promise<ApplicationProfileStatus> {
  if (!USE_MOCK) return apiRequest<ApplicationProfileStatus>('/application-profile')
  return delay({
    ready: false,
    verificationStatus: 'mock_mode',
    message: '演示模式不会读取本机私有画像，也不会生成真实申请材料。',
  })
}

export async function getApplications(): Promise<ApplicationTask[]> {
  if (!USE_MOCK) return apiRequest<ApplicationTask[]>('/applications')
  return delay([])
}

export async function getApplication(id: string): Promise<ApplicationTask> {
  if (!USE_MOCK) return apiRequest<ApplicationTask>(`/applications/${encodeURIComponent(id)}`)
  throw new ApiError(404, '演示模式中没有真实申请任务')
}

export async function getJobApplications(jobId: string): Promise<ApplicationTask[]> {
  if (!USE_MOCK) {
    return apiRequest<ApplicationTask[]>(`/jobs/${encodeURIComponent(jobId)}/applications`)
  }
  return delay([])
}

function requireRealMode(): void {
  if (USE_MOCK) {
    throw new ApiError(501, '演示模式不会调用大模型或生成真实申请材料')
  }
}

export async function createApplication(jobId: string): Promise<AcceptedAction> {
  requireRealMode()
  return apiRequest(`/jobs/${encodeURIComponent(jobId)}/applications`, { method: 'POST' })
}

export async function approveApplication(id: string): Promise<AcceptedAction> {
  requireRealMode()
  return apiRequest(`/applications/${encodeURIComponent(id)}/approve`, { method: 'POST' })
}

export async function resumeApplication(id: string): Promise<AcceptedAction> {
  requireRealMode()
  return apiRequest(`/applications/${encodeURIComponent(id)}/resume`, { method: 'POST' })
}

export async function renderApplication(id: string): Promise<AcceptedAction> {
  requireRealMode()
  return apiRequest(`/applications/${encodeURIComponent(id)}/render`, { method: 'POST' })
}

export async function rejectApplication(id: string): Promise<AcceptedAction> {
  requireRealMode()
  return apiRequest(`/applications/${encodeURIComponent(id)}/reject`, { method: 'POST' })
}

export async function downloadApplicationArtifact(
  artifact: ApplicationTask['artifacts'][number],
): Promise<void> {
  requireRealMode()
  return apiDownload(artifact.downloadUrl, artifact.fileName)
}
