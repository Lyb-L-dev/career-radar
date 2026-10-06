import { apiRequest } from './config'

export interface GrowthReference {
  targetId: string; requirementId: string; title: string; quote: string
  focus: boolean; minimumLevel: number; kind: 'skill' | 'hard' | 'bonus'
}
export interface GrowthPoint {
  id: string; name: string; status: 'unassessed' | 'independent' | 'needs_hint' | 'not_learned'
  evidenceId: string | null
}
export interface GrowthSkill {
  id: string; name: string; group: string; dependencies: string[]; points: GrowthPoint[]
  level: number; highestLevel: number; status: 'unverified' | 'developing' | 'mastered' | 'needs_practice'
  relevant: boolean; recommended: boolean; references: GrowthReference[]; reason: string
  selfReported: string[]; lastRecall: string | null; streak: number; nextReview: string | null
  reviewDue: boolean; proofIds: string[]; evidenceCount: number; rubricVersion: string
}
export interface GradePoint { pointId: string; passed: boolean; answerQuote: string; reason: string }
export interface GrowthEvidence {
  id: string; skillId: string; type: 'recall' | 'project' | 'interview'; createdAt: string
  question?: string; questionCode?: string; answer?: string; code?: string; explanation?: string; runRecord?: string
  points: GradePoint[]; passed: boolean; assisted?: boolean; skipped?: boolean; mode?: string
  feedback: string; teaching?: string; verification?: string; rubricVersion: string
}
export interface GrowthQuestion {
  id: string; skillId: string; text: string; code?: string; pointIds: string[]; mode: string; assisted: boolean
  answered: boolean; submittedAnswer?: string; hint?: string; feedback?: string; teaching?: string
  points?: GradePoint[]; passed?: boolean; evidenceId?: string
}
export interface GrowthSession {
  id: string; kind: 'baseline' | 'recall' | 'interview'; status: 'generating' | 'active' | 'completed'
  questions: GrowthQuestion[]; currentIndex: number; createdAt: string
}
export interface GrowthOperation {
  id: string; kind: string; status: 'queued' | 'running' | 'completed' | 'failed'
  error: string | null; result: { sessionId?: string; evidenceId?: string } | null; createdAt: string
}
export interface GrowthRequirement {
  id: string; skill: string; skillId: string | null; quote: string; kind: 'skill' | 'hard' | 'bonus'
  minimumLevel: number; level: number | null; status: 'qualification' | 'stale' | 'unverified' | 'gap' | 'supported'
  proofIds: string[]
}
export interface GrowthTarget {
  id: string; source: 'official' | 'boss' | 'manual'; sourceId: string; title: string; company: string
  description: string; url: string; focus: boolean; active: boolean; requirements: GrowthRequirement[]
  analysisStale: boolean; analyzedAt?: string; sourceUpdatedAt?: string
  eligibility: { verdict?: string; label?: string }
}
export interface GrowthTask {
  id: string; kind: 'learning' | 'project'; skillId: string; title: string; description: string
  criteria: string[]; reason: string; references: GrowthReference[]; reviewSkillIds: string[]
  status: 'todo' | 'partial' | 'done' | 'blocked'; blocker: string; output: string
}
export interface GrowthPlan { id: string; date: string; tasks: GrowthTask[]; revision: number }
export interface GrowthSnapshot {
  today: string; groups: string[]; levels: string[]; skills: GrowthSkill[]; targets: GrowthTarget[]
  sampleCount: number; sampleNotice: string; nextSkillId: string | null; plan: GrowthPlan | null
  settings: { dailyMinutes: number }; sessions: GrowthSession[]; operations: GrowthOperation[]
}
export interface GrowthSource { source: 'official' | 'boss'; id: string; title: string; company: string; url: string; jdComplete: boolean }

const post = <T,>(path: string, body: unknown) => apiRequest<T>(`/growth${path}`, { method: 'POST', body: JSON.stringify(body) })
const requestId = () => crypto.randomUUID()
export const getGrowth = () => apiRequest<GrowthSnapshot>('/growth')
export const getGrowthSources = () => apiRequest<GrowthSource[]>('/growth/sources')
export const getGrowthSkill = (id: string) => apiRequest<GrowthSkill & { evidence: GrowthEvidence[] }>(`/growth/skills/${encodeURIComponent(id)}`)
export const getGrowthSession = (id: string) => apiRequest<GrowthSession>(`/growth/sessions/${encodeURIComponent(id)}`)
export const getGrowthOperation = (id: string) => apiRequest<GrowthOperation>(`/growth/operations/${encodeURIComponent(id)}`)
export const getGrowthHistory = () => apiRequest<GrowthPlan[]>('/growth/plans')
export const addGrowthTarget = (body: { source: 'official' | 'boss' | 'manual'; id?: string; title?: string; company?: string; description?: string }) => post<GrowthTarget>('/targets', body)
export const updateGrowthTarget = (id: string, body: { focus?: boolean; active?: boolean; title?: string; description?: string }) => apiRequest(`/growth/targets/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) })
export const refreshGrowthTarget = (id: string) => post(`/targets/${encodeURIComponent(id)}/refresh`, {})
export const analyzeGrowth = (targetIds: string[] = []) => post<GrowthOperation>('/analyze', { targetIds, requestId: requestId() })
export const startGrowthSession = (skillIds: string[], kind: 'recall' | 'baseline' = 'recall') => post<GrowthOperation>('/sessions', { skillIds, kind, requestId: requestId() })
export const submitGrowthAnswer = (sessionId: string, questionId: string, answer: string, skipped = false) => post<GrowthOperation>(`/sessions/${sessionId}/answers`, { questionId, answer, skipped, requestId: requestId() })
export const requestGrowthHint = (sessionId: string, questionId: string) => post<GrowthOperation>(`/sessions/${sessionId}/hint`, { questionId, requestId: requestId() })
export const submitGrowthProject = (body: { skillId: string; code: string; explanation: string; runRecord: string }) => post<GrowthOperation>('/projects', { ...body, requestId: requestId() })
export const retryGrowthOperation = (id: string) => post<GrowthOperation>(`/operations/${id}/retry`, {})
export const ensureGrowthPlan = (adjust = false) => post<GrowthPlan>('/plans/today', { adjust })
export const reflectGrowthTask = (date: string, task: GrowthTask) => apiRequest(`/growth/plans/${date}/tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: task.status, blocker: task.blocker, output: task.output }) })
export const saveGrowthSettings = (dailyMinutes: number) => apiRequest('/growth/settings', { method: 'PUT', body: JSON.stringify({ dailyMinutes }) })
export const markGrowthPoint = (skillId: string, pointId: string, notLearned: boolean) => apiRequest(`/growth/skills/${skillId}/points/${pointId}`, { method: 'PUT', body: JSON.stringify({ notLearned }) })
