import { apiRequest } from './config';
import type { NotificationItem } from '@/types';
export async function getNotifications(): Promise<NotificationItem[]> {
    return apiRequest('/notifications');
}
export async function markRead(id: string): Promise<{
    ok: boolean;
}> {
    return apiRequest(`/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' });
}
export async function markAllRead(): Promise<{
    ok: boolean;
}> {
    return apiRequest('/notifications/read-all', { method: 'POST' });
}
export async function removeNotification(id: string): Promise<{
    ok: boolean;
}> {
    return apiRequest(`/notifications/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
