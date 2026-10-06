import { beforeEach, describe, expect, it } from 'vitest'
import {
  ALL_FILTER_VALUE,
  jobFilterValuesFromParams,
  jobFilterValuesToParams,
  loadSavedJobFilters,
  saveJobFilters,
} from './jobFilters'

describe('job filter persistence', () => {
  beforeEach(() => window.localStorage.clear())

  it('defaults to priority and retains unknown eligibility instead of excluding it', () => {
    const initial = jobFilterValuesFromParams(new URLSearchParams())
    expect(initial.tab).toBe('all')
    expect(initial.eligibility).toBe('available')
    expect(initial.sort).toBe('priority')
    const invalid = jobFilterValuesFromParams(new URLSearchParams('eligibility=garbage&sort=garbage'))
    expect(invalid.eligibility).toBe('available')
    expect(invalid.sort).toBe('priority')
  })

  it('round-trips active filters through URL parameters', () => {
    const values = {
      ...jobFilterValuesFromParams(new URLSearchParams()),
      tab: 'updated' as const,
      keyword: 'Python',
      companyType: 'central_soe',
      city: '福州',
    }
    const restored = jobFilterValuesFromParams(jobFilterValuesToParams(values))

    expect(restored).toEqual(values)
    expect(jobFilterValuesToParams(values).has('company')).toBe(false)
    expect(restored.companyId).toBe(ALL_FILTER_VALUE)
  })

  it('saves and restores filters locally', () => {
    const values = {
      ...jobFilterValuesFromParams(new URLSearchParams()),
      keyword: '数据',
      maxDifficulty: '5',
    }
    saveJobFilters(values)

    expect(loadSavedJobFilters()).toEqual(values)
  })
})
