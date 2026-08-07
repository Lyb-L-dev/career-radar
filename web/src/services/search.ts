import { apiRequest, delay, copy, USE_MOCK } from './config'
import { jobs } from '@/mocks/jobs'
import { companies } from '@/mocks/companies'
import { reports } from '@/mocks/reports'
import { runs } from '@/mocks/runs'
import { companyMatchesKeyword, jobMatchesKeyword } from '@/lib/jobSearch'
import type { SearchResults } from '@/types'

export async function globalSearch(keyword: string, limit = 20): Promise<SearchResults> {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return delay({ jobs: [], companies: [], reports: [], runs: [] }, 100, 200)
  if (!USE_MOCK) {
    return apiRequest(`/search?q=${encodeURIComponent(keyword)}&limit=${limit}`)
  }

  const matchedJobs = jobs
    .filter((j) => jobMatchesKeyword(j, kw))
    .slice(0, limit)

  const matchedCompanies = companies
    .filter((c) => companyMatchesKeyword(c, kw))
    .slice(0, limit)

  const matchedReports = reports
    .filter((r) => [r.date, r.summary].join(' ').toLowerCase().includes(kw))
    .slice(0, limit)

  const matchedRuns = runs
    .filter((r) => [r.code, r.status, r.trigger].join(' ').toLowerCase().includes(kw))
    .slice(0, limit)

  return delay(copy({ jobs: matchedJobs, companies: matchedCompanies, reports: matchedReports, runs: matchedRuns }))
}
