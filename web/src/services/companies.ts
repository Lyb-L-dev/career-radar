import { apiRequest } from './config';
import type { Company, CompanyError, CompanyPageRecord, CompanyPriority, CompanyTestResult, IndustryCategory, MonitorMode } from '@/types';
export async function getCompanies(): Promise<Company[]> {
    return apiRequest('/companies');
}
export async function getCompany(id: string): Promise<Company | undefined> {
    return apiRequest(`/companies/${encodeURIComponent(id)}`);
}
export interface NewCompanyInput {
    name: string;
    website: string;
    careersUrl?: string;
    companyType: Company['companyType'];
    industryCategory?: IndustryCategory;
    province?: string;
    city?: string;
    priority?: CompanyPriority;
    monitorMode?: MonitorMode;
    renderMode: Company['renderMode'];
    maxPages: number;
    enabled: boolean;
    note?: string;
}
export async function addCompany(input: NewCompanyInput): Promise<Company> {
    {
        return apiRequest('/companies', { method: 'POST', body: JSON.stringify(input) });
    }
}
export async function updateCompany(id: string, patch: Partial<Company>): Promise<{
    ok: boolean;
}> {
    {
        return apiRequest(`/companies/${encodeURIComponent(id)}`, {
            method: 'PATCH',
            body: JSON.stringify(patch),
        });
    }
}
export async function removeCompany(id: string): Promise<{
    ok: boolean;
}> {
    return apiRequest(`/companies/${encodeURIComponent(id)}`, { method: 'DELETE' });
}
export async function removeCompanies(ids: string[]): Promise<{
    ok: boolean;
    deleted: number;
}> {
    {
        return apiRequest('/companies/bulk-delete', {
            method: 'POST',
            body: JSON.stringify({ ids }),
        });
    }
}
export interface CompanyImportPreviewRow {
    rowNumber: number;
    name: string;
    url: string;
    status: 'valid' | 'duplicate' | 'invalid';
    errors: string[];
}
export interface CompanyImportPreview {
    rows: CompanyImportPreviewRow[];
    stats: {
        total: number;
        valid: number;
        duplicate: number;
        invalid: number;
    };
    canCommit: boolean;
}
export async function previewCompanyCsv(csvText: string): Promise<CompanyImportPreview> {
    {
        return apiRequest('/companies/import/preview', {
            method: 'POST',
            body: JSON.stringify({ csvText }),
        });
    }
}
export async function commitCompanyCsv(csvText: string): Promise<{
    ok: boolean;
    imported: number;
    skipped: number;
}> {
    {
        return apiRequest('/companies/import/commit', {
            method: 'POST',
            body: JSON.stringify({ csvText, confirmed: true }),
        });
    }
}
export async function testCompanyConnection(_website: string, _careersUrl?: string): Promise<CompanyTestResult> {
    {
        return apiRequest('/companies/test', {
            method: 'POST',
            body: JSON.stringify({ website: _website, careersUrl: _careersUrl }),
        });
    }
}
export async function getCompanyPageRecords(companyId: string): Promise<CompanyPageRecord[]> {
    return apiRequest(`/companies/${encodeURIComponent(companyId)}/pages`);
}
export async function getCompanyErrors(companyId: string): Promise<CompanyError[]> {
    return apiRequest(`/companies/${encodeURIComponent(companyId)}/errors`);
}
