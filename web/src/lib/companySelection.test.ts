import { describe, expect, it } from 'vitest'
import type { Company } from '@/types'
import { isUnmonitorable, selectionWouldDeleteAll } from './companySelection'

function company(id: string, status: Company['status']): Company {
  return { id, status } as Company
}

describe('company selection guards', () => {
  it('only classifies real monitoring failures as unmonitorable', () => {
    expect(isUnmonitorable(company('a', 'robots_blocked'))).toBe(true)
    expect(isUnmonitorable(company('b', 'structure_error'))).toBe(true)
    expect(isUnmonitorable(company('c', 'request_failed'))).toBe(true)
    expect(isUnmonitorable(company('d', 'paused'))).toBe(false)
    expect(isUnmonitorable(company('e', 'pending_verification'))).toBe(false)
  })

  it('blocks deleting every configured company', () => {
    const companies = [company('a', 'active'), company('b', 'paused')]
    expect(selectionWouldDeleteAll(companies, new Set(['a']))).toBe(false)
    expect(selectionWouldDeleteAll(companies, new Set(['a', 'b']))).toBe(true)
  })
})
