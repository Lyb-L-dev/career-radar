import type { Company } from '@/types'

const UNMONITORABLE_STATUSES = new Set<Company['status']>([
  'robots_blocked',
  'structure_error',
  'request_failed',
])

export function isUnmonitorable(company: Company): boolean {
  return UNMONITORABLE_STATUSES.has(company.status)
}

export function selectionWouldDeleteAll(
  companies: Company[],
  selectedIds: ReadonlySet<string>,
): boolean {
  return companies.length > 0 && companies.every((company) => selectedIds.has(company.id))
}
