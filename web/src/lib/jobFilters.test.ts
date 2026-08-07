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

