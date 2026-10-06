import { describe, expect, it } from 'vitest'
import { jobs } from '@/mocks/jobs'
import type { Job } from '@/types'
import type { PlatformLead } from '@/services/platformLeads'
import { bossOpportunities, officialOpportunities } from './opportunities'

describe('homepage source-specific opportunities', () => {
  it('does not promote handled or explicitly ineligible official jobs', () => {
    const job = (id: string, patch: Partial<Job> = {}): Job => ({ ...jobs[0], id, type: 'campus', isApplied: false, notInterested: false, status: 'new', abilityMatch: 'high', eligibility: undefined, ...patch })
    const result = officialOpportunities([job('applied', { isApplied: true }), job('closed', { status: 'closed' }), job('hidden', { notInterested: true }), job('good')])
    expect(result.map(item => item.id)).toEqual(['good'])
  })
  it('uses BOSS priority before review without mixing their scores with official jobs', () => {
    const lead = (id: string, category: PlatformLead['category'], patch: Partial<PlatformLead> = {}): PlatformLead => ({ id, category, title: id, company: '', location: '', salary: '', tags: '', description: '', source_url: '', jdComplete: true, companyIdentified: true, aiScreenable: true, firstSeenAt: '2026-10-01', lastSeenAt: '2026-10-05', isFavorite: false, isApplied: false, isHidden: false, score: 0, reasons: [], blockers: [], aiResult: null, aiCheckedAt: null, aiNeedsRefresh: false, ...patch })
    expect(bossOpportunities([lead('review', 'review', { score: 999 }), lead('priority', 'priority'), lead('handled', 'priority', { isApplied: true }), lead('excluded', 'excluded')]).map(item => item.id)).toEqual(['priority'])
    expect(bossOpportunities([lead('review', 'review'), lead('hidden', 'priority', { isHidden: true })]).map(item => item.id)).toEqual(['review'])
  })
})
