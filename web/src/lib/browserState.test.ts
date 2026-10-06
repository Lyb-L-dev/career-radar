import { describe, expect, it } from 'vitest'
import { formatLocalTime, jobDetailHref, safeJobsReturn } from './browserState'

describe('job detail navigation', () => {
  it('preserves the complete list query while rejecting external return destinations', () => {
    const from = '/jobs?source=official&q=Agent&city=上海&shown=120'
    const url = new URL(jobDetailHref('a/b', from), 'http://test')
    expect(url.pathname).toBe('/jobs/a%2Fb')
    const returned = new URL(url.searchParams.get('from')!, 'http://test')
    expect(returned.pathname).toBe('/jobs')
    expect(Object.fromEntries(returned.searchParams)).toEqual({ source: 'official', q: 'Agent', city: '上海', shown: '120' })
    for (const value of ['https://evil.test/jobs', '//evil.test/jobs', '/jobs/../../settings', 'javascript:alert(1)', '/settings']) expect(safeJobsReturn(value)).toBe('/jobs')
  })
  it('does not shift backend date-only review dates and formats instants in Beijing', () => {
    expect(formatLocalTime('2026-10-06')).toBe('2026-10-06')
    expect(formatLocalTime('2026-10-05T17:30:00Z')).toContain('10/06')
    expect(formatLocalTime(null)).toBe('尚无记录')
  })
})
