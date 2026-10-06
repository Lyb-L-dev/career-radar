import { matchFilter } from '@/services/jobs'
import type { Job } from '@/types'
import type { PlatformLead } from '@/services/platformLeads'

export function officialOpportunities(jobs: Job[]) {
  const available = jobs.filter(job => !job.isApplied && !job.notInterested && job.status !== 'closed' && job.type !== 'notice' && job.eligibility?.verdict !== 'ineligible')
  const groups = [available.filter(job => matchFilter(job, { tab: 'recommended' })), available.filter(job => job.eligibility?.verdict === 'review'), available.filter(job => matchFilter(job, { tab: 'unreviewed' }))]
  return (groups.find(group => group.length) ?? []).sort((a, b) => (b.priority?.score ?? -1) - (a.priority?.score ?? -1) || b.lastUpdatedAt.localeCompare(a.lastUpdatedAt)).slice(0, 3)
}
export function bossOpportunities(leads: PlatformLead[]) {
  const available = leads.filter(lead => !lead.isApplied && !lead.isHidden && lead.aiResult?.eligibility !== 'ineligible')
  const priority = available.filter(lead => lead.category === 'priority')
  return (priority.length ? priority : available.filter(lead => lead.category === 'review')).sort((a, b) => b.lastSeenAt.localeCompare(a.lastSeenAt)).slice(0, 3)
}
