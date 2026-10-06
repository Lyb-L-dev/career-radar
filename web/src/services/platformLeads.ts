import { apiRequest, USE_MOCK } from './config'

export type Category = 'priority' | 'review' | 'lower' | 'excluded'

export interface AIScreenResult {
  eligibility: 'eligible' | 'ineligible' | 'unknown'
  fit: 'strong' | 'reasonable' | 'weak' | 'unknown'
  action: 'prioritize' | 'consider' | 'defer'
  confidence: 'high' | 'medium' | 'low'
  summary: string
  eligibility_checks: {
    requirement: string
    verdict: 'met' | 'unmet' | 'unknown'
    job_quote: string
    candidate_quote: string
  }[]
  matched_evidence: string[]
  gaps: string[]
  next_step: string
}

export interface PlatformLead {
  id: string
  title: string
  company: string
  location: string
  salary: string
  tags: string
  description: string
  source_url: string
  jdComplete: boolean
  companyIdentified: boolean
  aiScreenable: boolean
  firstSeenAt: string
  lastSeenAt: string
  isFavorite: boolean
  isApplied: boolean
  isHidden: boolean
  score: number
  category: Category
  reasons: string[]
  blockers: string[]
  aiResult: AIScreenResult | null
  aiCheckedAt: string | null
  aiNeedsRefresh: boolean
}


export const PLATFORM_LEADS_KEY = ['platform-leads', 'list'] as const
export function getPlatformLeads(): Promise<PlatformLead[]> { return USE_MOCK ? Promise.resolve([]) : apiRequest('/platform-leads') }
