import { apiDownload, apiRequest } from './config';
import type { ApplicationProfileStatus, ApplicationTask } from '@/types';
type AcceptedAction = {
    ok: boolean;
    applicationId: string;
};
export async function getApplicationProfileStatus(): Promise<ApplicationProfileStatus> {
    return apiRequest<ApplicationProfileStatus>('/application-profile');
}
export async function getApplications(): Promise<ApplicationTask[]> {
    return apiRequest<ApplicationTask[]>('/applications');
}
export async function getApplication(id: string): Promise<ApplicationTask> {
    return apiRequest<ApplicationTask>(`/applications/${encodeURIComponent(id)}`);
}
export async function getJobApplications(jobId: string): Promise<ApplicationTask[]> {
    {
        return apiRequest<ApplicationTask[]>(`/jobs/${encodeURIComponent(jobId)}/applications`);
    }
}
export async function createApplication(jobId: string): Promise<AcceptedAction> {
    return apiRequest(`/jobs/${encodeURIComponent(jobId)}/applications`, { method: 'POST' });
}
export async function approveApplication(id: string): Promise<AcceptedAction> {
    return apiRequest(`/applications/${encodeURIComponent(id)}/approve`, { method: 'POST' });
}
export async function resumeApplication(id: string): Promise<AcceptedAction> {
    return apiRequest(`/applications/${encodeURIComponent(id)}/resume`, { method: 'POST' });
}
export async function renderApplication(id: string): Promise<AcceptedAction> {
    return apiRequest(`/applications/${encodeURIComponent(id)}/render`, { method: 'POST' });
}
export async function rejectApplication(id: string): Promise<AcceptedAction> {
    return apiRequest(`/applications/${encodeURIComponent(id)}/reject`, { method: 'POST' });
}
export async function downloadApplicationArtifact(artifact: ApplicationTask['artifacts'][number]): Promise<void> {
    return apiDownload(artifact.downloadUrl, artifact.fileName);
}
export async function downloadFormPilotProfile(applicationId: string): Promise<void> {
    return apiDownload(`/applications/${encodeURIComponent(applicationId)}/formpilot-profile`, 'career-radar-formpilot.json', { method: 'POST' });
}
