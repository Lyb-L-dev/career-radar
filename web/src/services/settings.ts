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
  backupName?: string
  includedFiles?: number
  sizeBytes?: number
  removed?: number
  cleared?: number
  prunedBackups?: number
}

export interface BackupItem {
  name: string
  createdAt: string
  sizeBytes: number
  includedFiles: number | null
  integrityStatus: 'unchecked' | 'valid' | 'invalid'
}

export interface BackupVerification {
  ok: boolean
  name: string
  integrityStatus: 'valid' | 'invalid'
  checkedFiles: number
  databaseIntegrity: 'ok' | 'not_present' | 'not_checked'
  message: string
}

const mockBackups: BackupItem[] = []

export async function runMaintenance(action: 'export' | 'clearLogs' | 'rebuildIndex' | 'recalcMatch' | 'cleanReports'): Promise<MaintenanceResult> {
  if (!USE_MOCK) return apiRequest(`/settings/maintenance/${action}`, { method: 'POST' })
  if (action === 'export') {
    const now = new Date()
    const date = now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '-')
    const name = `career-radar-backup-${date}-${String(now.getMilliseconds() * 1000).padStart(6, '0')}.zip`
    const backup: BackupItem = {
      name,
      createdAt: now.toISOString(),
      sizeBytes: 2048,
      includedFiles: 12,
      integrityStatus: 'unchecked',
    }
    mockBackups.unshift(backup)
    const prunedBackups = Math.max(0, mockBackups.length - settings.basic.backupRetentionCount)
    mockBackups.splice(settings.basic.backupRetentionCount)
    return delay({
      ok: true,
      message: `本地备份已创建：${name}`,
      backupName: name,
      includedFiles: backup.includedFiles ?? 0,
      sizeBytes: backup.sizeBytes,
      prunedBackups,
    }, 600, 1200)
  }
  const messages: Record<string, string> = {
    clearLogs: '运行日志已清空，历史任务统计保留。',
    rebuildIndex: '岗位索引已重建完成。',
    recalcMatch: '已按当前画像重新计算全部岗位匹配度。',
    cleanReports: '超出保留期的历史日报已清理。',
  }
  return delay({ ok: true, message: messages[action] }, 600, 1200)
}

export async function getBackups(): Promise<BackupItem[]> {
  if (!USE_MOCK) return apiRequest('/settings/backups')
  return delay(copy(mockBackups))
}

export async function verifyBackup(name: string): Promise<BackupVerification> {
  if (!USE_MOCK) {
    return apiRequest(`/settings/backups/${encodeURIComponent(name)}/verify`, { method: 'POST' })
  }
  const backup = mockBackups.find((item) => item.name === name)
  if (backup) backup.integrityStatus = 'valid'
  return delay({
    ok: true,
    name,
    integrityStatus: 'valid',
    checkedFiles: 8,
    databaseIntegrity: 'ok',
    message: '备份完整性校验通过',
  })
}

export async function deleteBackup(name: string, confirmed: boolean): Promise<{ ok: boolean; name: string; message: string }> {
  if (!USE_MOCK) {
    return apiRequest(`/settings/backups/${encodeURIComponent(name)}`, {
      method: 'DELETE',
      body: JSON.stringify({ confirmed }),
    })
  }
  if (!confirmed) throw new Error('请先确认删除这份本地备份')
  const index = mockBackups.findIndex((backup) => backup.name === name)
  if (index >= 0) mockBackups.splice(index, 1)
  return delay({ ok: true, name, message: '本地备份已删除' })
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
