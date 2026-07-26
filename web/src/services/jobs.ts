import { apiRequest, delay, copy, USE_MOCK } from './config'
import { jobs } from '@/mocks/jobs'
import type { Job, JobFilter } from '@/types'

function matchFilter(job: Job, filter: JobFilter): boolean {
  if (filter.tab === 'notice' && job.type !== 'notice') return false
  if (filter.tab === 'new' && job.status !== 'new') return false
  if (filter.tab === 'updated' && job.status !== 'updated') return false
  if (filter.tab === 'favorite' && !job.isFavorite) return false
  if (filter.tab === 'recommended') {
    const good = job.abilityMatch === 'high' || job.abilityMatch === 'medium'
    if (!(good && job.status !== 'closed' && !job.notInterested)) return false
  }
  if (filter.keyword) {
    const kw = filter.keyword.toLowerCase()
    const hay = [job.title, job.companyName, job.city, job.jdText, ...job.tags].join(' ').toLowerCase()
    if (!hay.includes(kw)) return false
  }
  if (filter.companyId && job.companyId !== filter.companyId) return false
  if (filter.companyType && job.companyType !== filter.companyType) return false
  if (filter.industryCategory && job.companyIndustry !== filter.industryCategory) return false
  if (filter.province && job.companyProvince !== filter.province) return false
  if (filter.city && job.city !== filter.city) return false
  if (filter.type && job.type !== filter.type) return false
  if (filter.gradYearMatch && job.gradYearMatch !== filter.gradYearMatch) return false
  if (filter.abilityMatch && job.abilityMatch !== filter.abilityMatch) return false
  if (filter.difficultyMax !== undefined && job.difficulty > filter.difficultyMax) return false
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
  list.sort((a, b) => b.lastUpdatedAt.localeCompare(a.lastUpdatedAt))
  return USE_MOCK ? delay(copy(list)) : list
}

export async function getJobCounts(): Promise<Record<string, number>> {
  const source = USE_MOCK ? copy(jobs) : await apiRequest<Job[]>('/jobs')
  const count = (tab: JobFilter['tab']) => source.filter((j) => matchFilter(j, { tab })).length
  const result = {
    recommended: count('recommended'),
    notice: count('notice'),
    new: count('new'),
    updated: count('updated'),
    all: source.length,
    favorite: source.filter((j) => j.isFavorite).length,
  }
  return USE_MOCK ? delay(result) : result
}

export async function getJob(id: string): Promise<Job | undefined> {
  if (!USE_MOCK) return apiRequest<Job>(`/jobs/${encodeURIComponent(id)}`)
  return delay(copy(jobs.find((j) => j.id === id)))
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

export async function favoriteMany(ids: string[]): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/jobs/favorite-many', { method: 'POST', body: JSON.stringify({ ids }) })
  }
  jobs.forEach((j) => {
    if (ids.includes(j.id)) j.isFavorite = true
  })
  return delay({ ok: true }, 100, 300)
}
