import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as runsApi from '@/services/runs'
import * as reportsApi from '@/services/reports'
import * as notificationsApi from '@/services/notifications'
import * as settingsApi from '@/services/settings'
import * as dashboardApi from '@/services/dashboard'
import * as searchApi from '@/services/search'
import type { AppSettings, CandidateProfile } from '@/types'
import { isActiveRunStatus } from '@/lib/runStatus'
import { pollingInterval } from '@/lib/polling'

// ---------- 总览 ----------
export function useDashboardStats() {
  return useQuery({ queryKey: ['dashboard'], queryFn: dashboardApi.getDashboardStats })
}

// ---------- 运行 ----------
export function useRuns() {
  return useQuery({
    queryKey: ['runs'],
    queryFn: runsApi.getRuns,
    refetchInterval: (query) =>
      pollingInterval(
        Boolean(query.state.data?.some((run) => isActiveRunStatus(run.status))),
        Boolean(query.state.error),
        3_000,
      ),
  })
}

export function useRun(id: string) {
  return useQuery({
    queryKey: ['run', id],
    queryFn: () => runsApi.getRun(id),
    refetchInterval: (query) =>
      pollingInterval(
        Boolean(query.state.data && isActiveRunStatus(query.state.data.status)),
        Boolean(query.state.error),
        3_000,
      ),
  })
}

// ---------- 日报 ----------
export function useReports() {
  return useQuery({ queryKey: ['reports'], queryFn: reportsApi.getReports })
}

export function useReport(date: string) {
  return useQuery({ queryKey: ['report', date], queryFn: () => reportsApi.getReport(date) })
}

// ---------- 通知 ----------
export function useNotifications() {
  return useQuery({ queryKey: ['notifications'], queryFn: notificationsApi.getNotifications })
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: async () => {
      const list = await notificationsApi.getNotifications()
      return list.filter((n) => !n.read).length
    },
    refetchInterval: 30000,
  })
}

export function useNotificationActions() {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ['notifications'] })
  const markRead = useMutation({ mutationFn: (id: string) => notificationsApi.markRead(id), onSuccess: invalidate })
  const markAll = useMutation({ mutationFn: () => notificationsApi.markAllRead(), onSuccess: invalidate })
  const remove = useMutation({ mutationFn: (id: string) => notificationsApi.removeNotification(id), onSuccess: invalidate })
  return { markRead, markAll, remove }
}

// ---------- 用户画像 ----------
export function useProfile() {
  return useQuery({ queryKey: ['profile'], queryFn: settingsApi.getProfile })
}

export function useSaveProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: CandidateProfile) => settingsApi.saveProfile(p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile'] }),
  })
}

// ---------- 系统设置 ----------
export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: settingsApi.getSettings })
}

export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (s: AppSettings) => settingsApi.saveSettings(s),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  })
}

// ---------- 全局搜索 ----------
export function useGlobalSearch(keyword: string) {
  return useQuery({
    queryKey: ['search', keyword],
    queryFn: () => searchApi.globalSearch(keyword),
    enabled: keyword.trim().length > 0,
  })
}
