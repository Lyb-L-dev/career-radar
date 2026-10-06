import type { Report } from '@/types'

export type ReportFileFilter = 'all' | 'complete' | 'incomplete'

export interface ReportFilters {
  date: string
  fileStatus: ReportFileFilter
  highMatchOnly: boolean
}

export function filterReports(reports: Report[], filters: ReportFilters): Report[] {
  return reports.filter((report) => {
    if (filters.date && report.date !== filters.date) return false
    const filesComplete = report.markdownStatus === 'generated' && report.csvStatus === 'generated'
    if (filters.fileStatus === 'complete' && !filesComplete) return false
    if (filters.fileStatus === 'incomplete' && filesComplete) return false
    if (filters.highMatchOnly && report.highMatchJobs === 0) return false
    return true
  })
}
