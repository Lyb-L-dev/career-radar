import { apiRequest, delay, copy, USE_MOCK } from './config'
import { jobs } from '@/mocks/jobs'
import { jobMatchesKeyword } from '@/lib/jobSearch'
import type { Job, JobFilter, SimilarJob, OfficialScreeningStatus } from '@/types'

export function matchFilter(job: Job, filter: JobFilter): boolean {
  if (filter.eligibility === 'available' && job.eligibility?.verdict === 'ineligible') return false
  if (filter.eligibility && filter.eligibility !== 'available' && (job.eligibility?.verdict ?? 'review') !== filter.eligibility) return false
  if (filter.tab === 'unreviewed' && (
    job.type === 'notice' || (job.aiAssessment ? job.aiAssessment.status === 'current' || job.eligibility?.verdict === 'ineligible' : job.abilityMatch !== 'unknown') || job.status === 'closed' || job.notInterested
  )) return false
  if (filter.tab === 'notice' && job.type !== 'notice') return false
  if (filter.tab === 'new' && job.status !== 'new') return false
  if (filter.tab === 'updated' && job.status !== 'updated') return false
  if (filter.tab === 'favorite' && !job.isFavorite) return false
  if (filter.tab === 'recommended') {
    if (job.eligibility && (job.eligibility.verdict !== 'eligible' || !['high', 'medium'].includes(job.priority?.tier ?? ''))) return false
    const good = job.abilityMatch === 'high' || job.abilityMatch === 'medium'
    if (!(good && job.status !== 'closed' && !job.notInterested)) return false
  }
  if (filter.keyword) {
    if (!jobMatchesKeyword(job, filter.keyword)) return false
  }
  if (filter.companyId && job.companyId !== filter.companyId) return false
  if (filter.companyType && job.companyType !== filter.companyType) return false
  if (filter.industryCategory && job.companyIndustry !== filter.industryCategory) return false
  if (filter.province && job.companyProvince !== filter.province) return false
  if (filter.city && job.city !== filter.city) return false
  if (filter.type && job.type !== filter.type) return false
  if (filter.gradYearMatch && job.gradYearMatch !== filter.gradYearMatch) return false
  if (filter.abilityMatch && job.abilityMatch !== filter.abilityMatch) return false
  if (filter.difficultyMax !== undefined && (
    job.abilityMatch === 'unknown' || job.difficultyEvaluated === false || job.difficulty > filter.difficultyMax
  )) return false
  if (filter.changedWithinDays !== undefined) {
    const t = new Date(job.lastUpdatedAt.replace(' ', 'T')).getTime()
    const days = (Date.now() - t) / 86400000
    if (days > filter.changedWithinDays) return false
  }
  if (filter.hasApplyUrl && !job.hasApplyUrl) return false
  return true
}

export async function getJobs(filter: JobFilter): Promise<Job[]> {
  const source = USE_MOCK ? copy(jobs) : await apiRequest<Job[]>('/jobs')
  const list = source.filter((j) => matchFilter(j, filter))
  list.sort((a, b) => {
    if (filter.sort !== 'updated') {
      const order = { eligible: 0, review: 1, ineligible: 2 }
      const eligibilityOrder = order[a.eligibility?.verdict ?? 'review'] - order[b.eligibility?.verdict ?? 'review']
      if (eligibilityOrder) return eligibilityOrder
      const scoreOrder = (b.priority?.score ?? -1) - (a.priority?.score ?? -1)
      if (scoreOrder) return scoreOrder
    }
    return b.lastUpdatedAt.localeCompare(a.lastUpdatedAt)
  })
  return USE_MOCK ? delay(copy(list)) : list
}

export async function getJobCounts(): Promise<Record<string, number>> {
  const source = USE_MOCK ? copy(jobs) : await apiRequest<Job[]>('/jobs')
  const count = (tab: JobFilter['tab']) => source.filter((j) => matchFilter(j, { tab })).length
  const result = {
    recommended: count('recommended'),
    unreviewed: count('unreviewed'),
    notice: count('notice'),
    new: count('new'),
    updated: count('updated'),
    all: source.length,
    favorite: source.filter((j) => j.isFavorite).length,
  }
  return USE_MOCK ? delay(result) : result
}

export async function getOfficialScreeningStatus(): Promise<OfficialScreeningStatus> {
  if (USE_MOCK) return { status: 'idle', total: 0, processed: 0, evaluated: 0, cached: 0, ineligible: 0, failed: 0, skipped: 0 }
  return apiRequest('/jobs/screening')
}

export async function startOfficialScreening(ids?: string[], force = false): Promise<OfficialScreeningStatus> {
  if (USE_MOCK) throw new Error('演示模式不会调用模型评估')
  return apiRequest('/jobs/screening', { method: 'POST', body: JSON.stringify({ ids, force }) })
}

export async function stopOfficialScreening(): Promise<OfficialScreeningStatus> {
  return apiRequest('/jobs/screening', { method: 'DELETE' })
}

  export async function getJob(id: string): Promise<Job | undefined> {
    if (!USE_MOCK) return apiRequest<Job>(`/jobs/${encodeURIComponent(id)}`)
    return delay(copy(jobs.find((j) => j.id === id)))
  }

  export async function getSimilarJobs(id: string): Promise<SimilarJob[]> {
    if (!USE_MOCK) {
      return apiRequest<SimilarJob[]>(`/jobs/${encodeURIComponent(id)}/similar`)
    }
    const source = copy(jobs)
    const current = source.find((j) => j.id === id)
    if (!current) return delay([])
    const scored = source
      .filter((j) => j.id !== id)
      .map((j) => ({ ...j, similarity: Math.round((Math.random() * 0.45 + 0.2) * 100) / 100 }))
      .sort((a, b) => b.similarity - a.similarity)
      .slice(0, 5)
    return delay(scored)
  }

export async function toggleFavorite(id: string): Promise<{ isFavorite: boolean }> {
  if (!USE_MOCK) {
    const job = await getJob(id)
    return apiRequest(`/jobs/${encodeURIComponent(id)}/favorite`, {
      method: 'POST',
      body: JSON.stringify({ value: !job?.isFavorite }),
    })
  }
  const job = jobs.find((j) => j.id === id)
  if (job) job.isFavorite = !job.isFavorite
  return delay({ isFavorite: job?.isFavorite ?? false }, 100, 250)
}

export async function markApplied(id: string, applied: boolean): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest(`/jobs/${encodeURIComponent(id)}/applied`, {
      method: 'POST',
      body: JSON.stringify({ value: applied }),
    })
  }
  const job = jobs.find((j) => j.id === id)
  if (job) job.isApplied = applied
  return delay({ ok: true }, 100, 250)
}

export async function markNotInterested(ids: string[]): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/jobs/not-interested', { method: 'POST', body: JSON.stringify({ ids }) })
  }
  jobs.forEach((j) => {
    if (ids.includes(j.id)) j.notInterested = true
  })
  return delay({ ok: true }, 100, 300)
}

export async function ignoreJobUpdate(id: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest(`/jobs/${encodeURIComponent(id)}/ignore-update`, {
      method: 'POST',
    })
  }
  const job = jobs.find((j) => j.id === id)
  if (job) job.status = 'ignored'
  return delay({ ok: true }, 100, 250)
}

export async function favoriteMany(ids: string[]): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/jobs/favorite-many', { method: 'POST', body: JSON.stringify({ ids }) })
  }
  jobs.forEach((j) => {
    if (ids.includes(j.id)) j.isFavorite = true
  })
  return delay({ ok: true }, 100, 300)
}
