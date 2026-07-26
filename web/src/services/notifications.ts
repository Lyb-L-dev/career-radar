import { apiRequest, delay, copy, USE_MOCK } from './config'
import { notifications } from '@/mocks/notifications'
import type { NotificationItem } from '@/types'

export async function getNotifications(): Promise<NotificationItem[]> {
  if (!USE_MOCK) return apiRequest('/notifications')
  const list = [...notifications].sort((a, b) => b.time.localeCompare(a.time))
  return delay(copy(list))
}

export async function markRead(id: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest(`/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' })
  const n = notifications.find((x) => x.id === id)
  if (n) n.read = true
  return delay({ ok: true }, 100, 200)
}

export async function markAllRead(): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest('/notifications/read-all', { method: 'POST' })
  notifications.forEach((n) => (n.read = true))
  return delay({ ok: true }, 150, 300)
}

export async function removeNotification(id: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest(`/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' })
  const idx = notifications.findIndex((x) => x.id === id)
  if (idx >= 0) notifications.splice(idx, 1)
  return delay({ ok: true }, 100, 250)
}
