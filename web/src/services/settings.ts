import { apiRequest, delay, copy, USE_MOCK } from './config'
import { profile, settings } from '@/mocks/profile'
import type { CandidateProfile, AppSettings } from '@/types'

export async function getProfile(): Promise<CandidateProfile> {
  if (!USE_MOCK) return apiRequest('/profile')
  return delay(copy(profile))
}

export async function saveProfile(input: CandidateProfile): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/profile', { method: 'PUT', body: JSON.stringify(input) })
  }
  Object.assign(profile, input)
  return delay({ ok: true }, 300, 500)
}

export async function recalculateMatch(): Promise<{ ok: boolean; updated: number }> {
  if (!USE_MOCK) return apiRequest('/profile/recalculate', { method: 'POST' })
  return delay({ ok: true, updated: 15 }, 800, 1400)
}

export async function getSettings(): Promise<AppSettings> {
  if (!USE_MOCK) return apiRequest('/settings')
  return delay(copy(settings))
}

export async function saveSettings(input: AppSettings): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest('/settings', { method: 'PUT', body: JSON.stringify(input) })
  }
  Object.assign(settings, input)
  return delay({ ok: true }, 300, 500)
}

export async function testLlmConnection(confirmed: boolean): Promise<{ ok: boolean; latencyMs: number; model: string }> {
  if (!USE_MOCK) {
    return apiRequest('/settings/test-llm', {
      method: 'POST',
      body: JSON.stringify({ confirmed }),
    })
  }
  return delay({ ok: true, latencyMs: 860, model: settings.llm.model }, 900, 1500)
}

  export async function sendTestEmail(): Promise<{ ok: boolean; message: string }> {
    if (!USE_MOCK) return apiRequest('/settings/test-email', { method: 'POST' })
    if (!settings.email.enabled || !settings.email.smtpHost) {
      return delay({ ok: false, message: 'SMTP 尚未配置完成，无法发送测试邮件。' }, 500, 800)
    }
    return delay({ ok: true, message: '测试邮件已发送，请在收件箱查收。' }, 800, 1200)
  }

  export async function sendTestApprise(): Promise<{ ok: boolean; message: string }> {
    if (!USE_MOCK) return apiRequest('/settings/test-apprise', { method: 'POST' })
    if (!settings.apprise.enabled || !settings.apprise.configured) {
      return delay({ ok: false, message: 'Apprise 尚未配置完成，无法发送测试推送。' }, 500, 800)
    }
    return delay({ ok: true, message: '测试推送已发送，请在对应渠道查收。' }, 800, 1200)
  }
  
  export interface MaintenanceResult {
  ok: boolean
  message: string
}

export async function runMaintenance(action: 'export' | 'clearLogs' | 'rebuildIndex' | 'recalcMatch' | 'cleanReports'): Promise<MaintenanceResult> {
  if (!USE_MOCK) return apiRequest(`/settings/maintenance/${action}`, { method: 'POST' })
  const messages: Record<string, string> = {
    export: '全部数据已导出为备份压缩包。',
    clearLogs: '运行日志已清空，历史任务统计保留。',
    rebuildIndex: '岗位索引已重建完成。',
    recalcMatch: '已按当前画像重新计算全部岗位匹配度。',
    cleanReports: '超出保留期的历史日报已清理。',
  }
  return delay({ ok: true, message: messages[action] }, 600, 1200)
}

export async function getDbStats(): Promise<{ jobs: number; history: number; reports: number; logs: number; sizeMb: number }> {
  if (!USE_MOCK) return apiRequest('/settings/db-stats')
  return delay({ jobs: 15, history: 21, reports: 5, logs: 128, sizeMb: 2.4 })
}

export interface AutomationStatus {
  supported: boolean
  platform: string
  taskName: string
  dailyRunTime: string
  installed: boolean
  state: string
  nextRunAt?: string | null
  lastRunAt?: string | null
  lastResult?: number | null
  startWhenAvailable: boolean
  allowOnBattery: boolean
  paidCallsRequireConfirmation: boolean
  message: string
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  if (!USE_MOCK) return apiRequest('/automation')
  return delay({
    supported: true,
    platform: 'Windows',
    taskName: 'Career Radar Daily Monitor',
    dailyRunTime: settings.basic.dailyRunTime,
    installed: false,
    state: 'not_installed',
    nextRunAt: null,
    lastRunAt: null,
    lastResult: null,
    startWhenAvailable: true,
    allowOnBattery: true,
    paidCallsRequireConfirmation: true,
    message: '将使用当前项目虚拟环境和 config.yaml，每天运行一次公开招聘监控。',
  })
}

export async function changeAutomation(
  action: 'install' | 'remove',
  dailyRunTime: string,
): Promise<AutomationStatus> {
  if (!USE_MOCK) {
    return apiRequest(`/automation/${action}`, {
      method: 'POST',
      body: JSON.stringify({ confirmed: true, dailyRunTime }),
    })
  }
  const current = await getAutomationStatus()
  return delay({
    ...current,
    installed: action === 'install',
    state: action === 'install' ? 'Ready' : 'not_installed',
  })
}
