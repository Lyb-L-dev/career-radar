import { apiRequest } from './config';
import type { CandidateProfile, AppSettings } from '@/types';
export async function getProfile(): Promise<CandidateProfile> {
    return apiRequest('/profile');
}
export async function saveProfile(input: CandidateProfile): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest('/profile', { method: 'PUT', body: JSON.stringify(input) });
    }
}
export async function recalculateMatch(): Promise<{
    ok: boolean;
    updated: number;
}> {
    return apiRequest('/profile/recalculate', { method: 'POST' });
}
export async function getSettings(): Promise<AppSettings> {
    return apiRequest('/settings');
}
export async function saveSettings(input: AppSettings): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest('/settings', { method: 'PUT', body: JSON.stringify(input) });
    }
}
export async function testLlmConnection(confirmed: boolean): Promise<{
    ok: boolean;
    latencyMs: number;
    model: string;
}> {
    {
        return apiRequest('/settings/test-llm', {
            method: 'POST',
            body: JSON.stringify({ confirmed }),
        });
    }
}
export async function sendTestEmail(): Promise<{
    ok: boolean;
    message: string;
}> {
    return apiRequest('/settings/test-email', { method: 'POST' });
}
export async function sendTestApprise(): Promise<{
    ok: boolean;
    message: string;
}> {
    return apiRequest('/settings/test-apprise', { method: 'POST' });
}
export interface MaintenanceResult {
    ok: boolean;
    message: string;
    backupName?: string;
    includedFiles?: number;
    sizeBytes?: number;
    removed?: number;
    cleared?: number;
    prunedBackups?: number;
}
export interface BackupItem {
    name: string;
    createdAt: string;
    sizeBytes: number;
    includedFiles: number | null;
    integrityStatus: 'unchecked' | 'valid' | 'invalid';
}
export interface BackupVerification {
    ok: boolean;
    name: string;
    integrityStatus: 'valid' | 'invalid';
    checkedFiles: number;
    databaseIntegrity: 'ok' | 'not_present' | 'not_checked';
    message: string;
}
export async function runMaintenance(action: 'export' | 'clearLogs' | 'rebuildIndex' | 'recalcMatch' | 'cleanReports'): Promise<MaintenanceResult> {
    return apiRequest(`/settings/maintenance/${action}`, { method: 'POST' });
}
export async function getBackups(): Promise<BackupItem[]> {
    return apiRequest('/settings/backups');
}
export async function verifyBackup(name: string): Promise<BackupVerification> {
    {
        return apiRequest(`/settings/backups/${encodeURIComponent(name)}/verify`, { method: 'POST' });
    }
}
export async function deleteBackup(name: string, confirmed: boolean): Promise<{
    ok: boolean;
    name: string;
    message: string;
}> {
    {
        return apiRequest(`/settings/backups/${encodeURIComponent(name)}`, {
            method: 'DELETE',
            body: JSON.stringify({ confirmed }),
        });
    }
}
export async function getDbStats(): Promise<{
    jobs: number;
    history: number;
    reports: number;
    logs: number;
    sizeMb: number;
}> {
    return apiRequest('/settings/db-stats');
}
export interface AutomationStatus {
    supported: boolean;
    platform: string;
    taskName: string;
    dailyRunTime: string;
    installed: boolean;
    state: string;
    nextRunAt?: string | null;
    lastRunAt?: string | null;
    lastResult?: number | null;
    startWhenAvailable: boolean;
    allowOnBattery: boolean;
    paidCallsRequireConfirmation: boolean;
    message: string;
}
export async function getAutomationStatus(): Promise<AutomationStatus> {
    return apiRequest('/automation');
}
export async function changeAutomation(action: 'install' | 'remove', dailyRunTime: string): Promise<AutomationStatus> {
    {
        return apiRequest(`/automation/${action}`, {
            method: 'POST',
            body: JSON.stringify({ confirmed: true, dailyRunTime }),
        });
    }
}
