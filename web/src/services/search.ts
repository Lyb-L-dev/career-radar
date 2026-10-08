import { apiRequest } from './config';
import type { SearchResults } from '@/types';
export async function globalSearch(keyword: string, limit = 20): Promise<SearchResults> {
    const kw = keyword.trim().toLowerCase();
    if (!kw)
        return { jobs: [], companies: [], reports: [], runs: [] };
    {
        return apiRequest(`/search?q=${encodeURIComponent(keyword)}&limit=${limit}`);
    }
}
