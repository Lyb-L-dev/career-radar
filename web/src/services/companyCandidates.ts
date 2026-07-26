import { apiRequest } from './config'
import type {
  Company,
  CompanyCandidate,
  CompanyCandidateDecision,
  CompanyCandidatePage,
  CompanyWebsiteDiscovery,
  CompanyType,
  IndustryCategory,
  MonitorMode,
  RecruitmentChannel,
  RecruitmentChannelStatus,
  RecruitmentMaterialType,
  RecruitmentSource,
  RecruitmentSourceKind,
  RecruitmentSourceVerification,
} from '@/types'

export interface CandidateFilters {
  q?: string
  province?: string
  city?: string
  fitLevel?: 'high' | 'medium' | 'low'
  decision?: CompanyCandidateDecision
  channelStatus?: RecruitmentChannelStatus
  sourceKey?: string
  techOnly?: boolean
  page?: number
  pageSize?: number
}

function queryString(filters: CandidateFilters): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value))
  })
  const value = params.toString()
  return value ? `?${value}` : ''
}

export async function getCompanyCandidates(filters: CandidateFilters): Promise<CompanyCandidatePage> {
  return apiRequest(`/company-candidates${queryString(filters)}`)
}

export async function getCompanyCandidate(id: string): Promise<CompanyCandidate> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}`)
}

export async function discoverCompanyWebsite(id: string): Promise<CompanyWebsiteDiscovery> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}/discover-website`, {
    method: 'POST',
  })
}

export interface CandidateReviewInput {
  decision: Exclude<CompanyCandidateDecision, 'monitored'>
  officialWebsite?: string | null
  careersUrl?: string | null
  companyType?: CompanyType
  industryCategory?: IndustryCategory
  recruitmentChannelStatus?: RecruitmentChannelStatus
  parentCompany?: string | null
  groupRecruitmentUrl?: string | null
  attributionKeywords?: string[] | null
  note?: string | null
}

export async function reviewCompanyCandidate(id: string, input: CandidateReviewInput): Promise<{ ok: boolean }> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export interface CandidateMonitorInput {
  website: string
  careersUrl?: string
  companyType: CompanyType
  industryCategory?: IndustryCategory
  monitorMode: MonitorMode
  maxPages: number
  enabled: boolean
  recruitmentChannel?: RecruitmentChannel
  parentCompany?: string
  attributionKeywords?: string[]
  note?: string
}

export async function monitorCompanyCandidate(id: string, input: CandidateMonitorInput): Promise<Company> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}/monitor`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function getCandidateSources(id: string): Promise<RecruitmentSource[]> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}/sources`)
}

export interface CandidateSourceInput {
  sourceKind: RecruitmentSourceKind
  verificationStatus: RecruitmentSourceVerification
  materialType: RecruitmentMaterialType
  title: string
  sourceUrl?: string
  content?: string
  publishedAt?: string
  parentCompany?: string
  importAsNotice: boolean
}

export async function addCandidateSource(
  id: string,
  input: CandidateSourceInput,
): Promise<RecruitmentSource> {
  return apiRequest(`/company-candidates/${encodeURIComponent(id)}/sources`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}
