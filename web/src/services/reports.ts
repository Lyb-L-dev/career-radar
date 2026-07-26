import { apiDownload, apiRequest, delay, copy, USE_MOCK } from './config'
import { reports } from '@/mocks/reports'
import type { Report } from '@/types'

export async function getReports(): Promise<Report[]> {
  if (!USE_MOCK) return apiRequest('/reports')
  return delay(copy(reports))
}

export async function getReport(date: string): Promise<Report | undefined> {
  if (!USE_MOCK) return apiRequest(`/reports/${encodeURIComponent(date)}`)
  return delay(copy(reports.find((r) => r.date === date)))
}

export async function generateReport(date?: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/reports/generate', { method: 'POST', body: JSON.stringify({ date }) })
  }
  return delay({ ok: true }, 600, 1000)
}

export async function resendReportEmail(date: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest(`/reports/${encodeURIComponent(date)}/resend`, { method: 'POST' })
  return delay({ ok: true }, 400, 700)
}

/** 触发浏览器下载一个模拟文件（Markdown / CSV） */
export function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob(['﻿' + content], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadReport(date: string, format: 'md' | 'csv'): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    await apiDownload(`/reports/${encodeURIComponent(date)}/download/${format}`, `${date}-jobs.${format}`)
    return { ok: true }
  }
  if (format === 'md') {
    downloadTextFile(
      `career-radar-${date}.md`,
      `# Career Radar 日报 · ${date}\n\n> 本文件为演示环境的示例导出内容。\n\n- 新增岗位与更新岗位的完整列表请以前端页面为准。\n`,
      'text/markdown',
    )
  } else {
    // CSV 使用 UTF-8 BOM，可直接使用 Excel 打开
    downloadTextFile(
      `career-radar-${date}.csv`,
      `职位名称,企业,城市,类型,难度,届别匹配,能力匹配,更新时间\nAI Agent 构建工程师（实习）,FIT2CLOUD 飞致云,上海,实习,5,高,中,2026-07-18 09:47\n`,
      'text/csv',
    )
  }
  return delay({ ok: true }, 200, 400)
}
