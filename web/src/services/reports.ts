import { apiDownload, apiRequest } from './config';
import type { Report } from '@/types';
export async function getReports(): Promise<Report[]> {
    return apiRequest('/reports');
}
export async function getReport(date: string): Promise<Report | undefined> {
    return apiRequest(`/reports/${encodeURIComponent(date)}`);
}
export async function generateReport(date?: string): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest('/reports/generate', { method: 'POST', body: JSON.stringify({ date }) });
    }
}
export interface ReportEmailResult {
    ok: boolean;
    message: string;
    eventCount: number;
    sentAt: string;
}
export async function resendReportEmail(date: string, confirmed: boolean): Promise<ReportEmailResult> {
    {
        return apiRequest(`/reports/${encodeURIComponent(date)}/resend`, {
            method: 'POST',
            body: JSON.stringify({ confirmed }),
        });
    }
}
export async function downloadReport(date: string, format: 'md' | 'csv'): Promise<{
    ok: boolean;
}> {
    {
        await apiDownload(`/reports/${encodeURIComponent(date)}/download/${format}`, `${date}-jobs.${format}`);
        return { ok: true };
    }
}

/** 下载文本文件，供运行日志导出使用。 */
export function downloadTextFile(filename: string, content: string, mime: string) {
  const blob = new Blob(['﻿' + content], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
