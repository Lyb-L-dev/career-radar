import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as reputationApi from '@/services/reputation'

const ACTIVE_STATUSES = new Set(['pending', 'running'])

export function useReputationHealth() {
  return useQuery({
    queryKey: ['reputation-health'],
    queryFn: reputationApi.getReputationHealth,
    staleTime: 30_000,
  })
}

export function useJobReputation(jobId: string) {
  return useQuery({
    queryKey: ['job-reputation', jobId],
    queryFn: () => reputationApi.getJobReputation(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ACTIVE_STATUSES.has(query.state.data?.status ?? '') ? 1_500 : false,
  })
}

export function useStartReputationScan(jobId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => reputationApi.startReputationScan(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job-reputation', jobId] })
      queryClient.invalidateQueries({ queryKey: ['reputation-health'] })
    },
  })
}
