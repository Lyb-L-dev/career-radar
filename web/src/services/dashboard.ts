import { apiRequest, delay, copy, USE_MOCK } from './config'
import { dashboardStats } from '@/mocks/profile'
import type { DashboardStats } from '@/types'

export async function getDashboardStats(): Promise<DashboardStats> {
  if (!USE_MOCK) return apiRequest('/dashboard')
  return delay(copy(dashboardStats))
}
