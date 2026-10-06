import { describe, expect, it } from 'vitest'
import { filterReports } from './reportFilters'
import type { Report } from '@/types'

function report(
  date: string,
  highMatchJobs: number,
  csvStatus: Report['csvStatus'] = 'generated',
): Report {
  return {
    date,
    newJobs: 1,
    updatedJobs: 0,
    highMatchJobs,
    markdownStatus: 'generated',
    csvStatus,
    emailStatus: 'disabled',
    summary: '',
    topJobIds: [],
    newJobIds: [],
    updatedJobIds: [],
    anomalies: [],
    tomorrowFocus: [],
  }
}

describe('report filters', () => {
  const reports = [
    report('2026-08-10', 2),
    report('2026-08-09', 0, 'none'),
    report('2026-08-08', 1, 'none'),
  ]

  it('combines date, file completeness, and high-match filters', () => {
    expect(filterReports(reports, {
      date: '2026-08-08',
      fileStatus: 'incomplete',
      highMatchOnly: true,
    })).toEqual([reports[2]])
  })

  it('returns all reports when filters are cleared', () => {
    expect(filterReports(reports, {
      date: '',
      fileStatus: 'all',
      highMatchOnly: false,
    })).toEqual(reports)
  })
})
