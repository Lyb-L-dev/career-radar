import { useQuery } from '@tanstack/react-query'
import { getPlatformLeads, PLATFORM_LEADS_KEY } from '@/services/platformLeads'
export function usePlatformLeads() { return useQuery({ queryKey: PLATFORM_LEADS_KEY, queryFn: getPlatformLeads }) }
