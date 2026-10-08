import { apiRequest } from './config';
import { jobMatchesKeyword } from '@/lib/jobSearch';
import type { Job, JobFilter, SimilarJob, OfficialScreeningStatus } from '@/types';
export function matchFilter(job: Job, filter: JobFilter): boolean {
    if (filter.eligibility === 'available' && job.eligibility?.verdict === 'ineligible')
        return false;
    if (filter.eligibility && filter.eligibility !== 'available' && (job.eligibility?.verdict ?? 'review') !== filter.eligibility)
        return false;
    if (filter.tab === 'unreviewed' && (job.type === 'notice' || (job.aiAssessment ? job.aiAssessment.status === 'current' || job.eligibility?.verdict === 'ineligible' : job.abilityMatch !== 'unknown') || job.status === 'closed' || job.notInterested))
        return false;
    if (filter.tab === 'notice' && job.type !== 'notice')
        return false;
    if (filter.tab === 'new' && job.status !== 'new')
        return false;
    if (filter.tab === 'updated' && job.status !== 'updated')
        return false;
    if (filter.tab === 'favorite' && !job.isFavorite)
        return false;
    if (filter.tab === 'recommended') {
        if (job.eligibility && (job.eligibility.verdict !== 'eligible' || !['high', 'medium'].includes(job.priority?.tier ?? '')))
            return false;
        const good = job.abilityMatch === 'high' || job.abilityMatch === 'medium';
        if (!(good && job.status !== 'closed' && !job.notInterested))
            return false;
    }
    if (filter.keyword) {
        if (!jobMatchesKeyword(job, filter.keyword))
            return false;
    }
    if (filter.companyId && job.companyId !== filter.companyId)
        return false;
    if (filter.companyType && job.companyType !== filter.companyType)
        return false;
    if (filter.industryCategory && job.companyIndustry !== filter.industryCategory)
        return false;
    if (filter.province && job.companyProvince !== filter.province)
        return false;
    if (filter.city && job.city !== filter.city)
        return false;
    if (filter.type && job.type !== filter.type)
        return false;
    if (filter.gradYearMatch && job.gradYearMatch !== filter.gradYearMatch)
        return false;
    if (filter.abilityMatch && job.abilityMatch !== filter.abilityMatch)
        return false;
    if (filter.difficultyMax !== undefined && (job.abilityMatch === 'unknown' || job.difficultyEvaluated === false || job.difficulty > filter.difficultyMax))
        return false;
    if (filter.changedWithinDays !== undefined) {
        const t = new Date(job.lastUpdatedAt.replace(' ', 'T')).getTime();
        const days = (Date.now() - t) / 86400000;
        if (days > filter.changedWithinDays)
            return false;
    }
    if (filter.hasApplyUrl && !job.hasApplyUrl)
        return false;
    return true;
}
export async function getJobs(filter: JobFilter): Promise<Job[]> {
    const source = await apiRequest<Job[]>('/jobs');
    const list = source.filter((j) => matchFilter(j, filter));
    list.sort((a, b) => {
        if (filter.sort !== 'updated') {
            const order = { eligible: 0, review: 1, ineligible: 2 };
            const eligibilityOrder = order[a.eligibility?.verdict ?? 'review'] - order[b.eligibility?.verdict ?? 'review'];
            if (eligibilityOrder)
                return eligibilityOrder;
            const scoreOrder = (b.priority?.score ?? -1) - (a.priority?.score ?? -1);
            if (scoreOrder)
                return scoreOrder;
        }
        return b.lastUpdatedAt.localeCompare(a.lastUpdatedAt);
    });
    return list;
}
export async function getJobCounts(): Promise<Record<string, number>> {
    const source = await apiRequest<Job[]>('/jobs');
    const count = (tab: JobFilter['tab']) => source.filter((j) => matchFilter(j, { tab })).length;
    const result = {
        recommended: count('recommended'),
        unreviewed: count('unreviewed'),
        notice: count('notice'),
        new: count('new'),
        updated: count('updated'),
        all: source.length,
        favorite: source.filter((j) => j.isFavorite).length,
    };
    return result;
}
export async function getOfficialScreeningStatus(): Promise<OfficialScreeningStatus> {
    return apiRequest('/jobs/screening');
}
export async function startOfficialScreening(ids?: string[], force = false): Promise<OfficialScreeningStatus> {
    return apiRequest('/jobs/screening', { method: 'POST', body: JSON.stringify({ ids, force }) });
}
export async function stopOfficialScreening(): Promise<OfficialScreeningStatus> {
    return apiRequest('/jobs/screening', { method: 'DELETE' });
}
export async function getJob(id: string): Promise<Job | undefined> {
    return apiRequest<Job>(`/jobs/${encodeURIComponent(id)}`);
}
export async function getSimilarJobs(id: string): Promise<SimilarJob[]> {
    {
        return apiRequest<SimilarJob[]>(`/jobs/${encodeURIComponent(id)}/similar`);
    }
}
export async function toggleFavorite(id: string): Promise<{
    isFavorite: boolean;
}> {
    {
        const job = await getJob(id);
        return apiRequest(`/jobs/${encodeURIComponent(id)}/favorite`, {
            method: 'POST',
            body: JSON.stringify({ value: !job?.isFavorite }),
        });
    }
}
export async function markApplied(id: string, applied: boolean): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest(`/jobs/${encodeURIComponent(id)}/applied`, {
            method: 'POST',
            body: JSON.stringify({ value: applied }),
        });
    }
}
export async function markNotInterested(ids: string[]): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest('/jobs/not-interested', { method: 'POST', body: JSON.stringify({ ids }) });
    }
}
export async function ignoreJobUpdate(id: string): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest(`/jobs/${encodeURIComponent(id)}/ignore-update`, {
            method: 'POST',
        });
    }
}
export async function favoriteMany(ids: string[]): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest('/jobs/favorite-many', { method: 'POST', body: JSON.stringify({ ids }) });
    }
}
