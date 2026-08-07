import type { Job } from '@/types'
import { JOB_STATUS_LABEL, JOB_TYPE_LABEL, MATCH_LEVEL_LABEL } from '@/types'

function csvCell(value: unknown): string {
  let text = value == null ? '' : String(value)
  if (/^[\s]*[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export function buildJobsCsv(jobs: Job[]): string {
  const headers = [
    '职位名称',
    '企业',
    '城市',
    '职位类型',
    '状态',
    '能力匹配',
    '难度',
    '发布时间',
    '最后更新',
    '申请链接',
    '来源链接',
  ]
  const rows = jobs.map((job) => [
    job.title,
    job.companyName,
    job.city,
    JOB_TYPE_LABEL[job.type],
    JOB_STATUS_LABEL[job.status],
    MATCH_LEVEL_LABEL[job.abilityMatch],
    job.difficulty,
    job.publishedAt,
    job.lastUpdatedAt,
    job.applyUrl,
    job.sourceUrl,
  ])
  return `\uFEFF${[headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')}`
}

export function downloadJobsCsv(jobs: Job[], filename: string): void {
  const blob = new Blob([buildJobsCsv(jobs)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
