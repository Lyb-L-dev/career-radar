import { describe, expect, it } from 'vitest'
import type { Job } from '@/types'
import { buildJobsCsv } from './jobExport'

describe('job CSV export', () => {
  it('escapes spreadsheet formulas and quotes', () => {
    const job = {
      title: '=HYPERLINK("bad")',
      companyName: '测试"公司',
      city: '福州',
      type: 'campus',
      status: 'new',
      abilityMatch: 'high',
      difficulty: 3,
      lastUpdatedAt: '2026-07-27T10:00:00+08:00',
      sourceUrl: 'https://example.com/job',
    } as Job

    const csv = buildJobsCsv([job])

    expect(csv).toContain(`"'=HYPERLINK(""bad"")"`)
    expect(csv).toContain(`"测试""公司"`)
    expect(csv.startsWith('\uFEFF')).toBe(true)
  })
})
