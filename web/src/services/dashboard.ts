import { apiRequest } from './config';
import type { DashboardStats } from '@/types';
export async function getDashboardStats(): Promise<DashboardStats> {
    return apiRequest('/dashboard');
}
