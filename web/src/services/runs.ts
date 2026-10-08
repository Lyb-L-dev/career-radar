import { apiRequest } from './config';
import type { Run } from '@/types';
export async function getRuns(): Promise<Run[]> {
    return apiRequest('/runs');
}
export async function getRun(id: string): Promise<Run | undefined> {
    return apiRequest(`/runs/${encodeURIComponent(id)}`);
}
export async function createRun(options: {
    scope: 'all' | 'failed' | 'company' | 'company_type';
    companyId?: string;
    companyType?: import('@/types').CompanyType;
    sendEmail: boolean;
}): Promise<{
    ok: boolean;
    runId: string;
}> {
    {
        return apiRequest('/runs', { method: 'POST', body: JSON.stringify(options) });
    }
}
export async function stopRun(id: string): Promise<{
    ok: boolean;
}> {
    return apiRequest(`/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' });
}
export async function retryFailed(id: string): Promise<{
    ok: boolean;
    runId?: string;
}> {
    return apiRequest(`/runs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
}
