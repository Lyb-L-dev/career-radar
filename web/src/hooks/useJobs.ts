import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import * as jobsApi from '@/services/jobs'
import type { JobFilter } from '@/types'

export function useJobs(filter: JobFilter) {
  return useQuery({
    queryKey: ['jobs', filter],
    queryFn: () => jobsApi.getJobs(filter),
  })
}

export function useJobCounts() {
  return useQuery({ queryKey: ['job-counts'], queryFn: jobsApi.getJobCounts })
}

  export function useJob(id: string) {
    return useQuery({ queryKey: ['job', id], queryFn: () => jobsApi.getJob(id) })
  }

  export function useSimilarJobs(id: string) {
    return useQuery({
      queryKey: ['job-similar', id],
      queryFn: () => jobsApi.getSimilarJobs(id),
      enabled: !!id,
    })
  }

function useInvalidateJobs() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['jobs'] })
    qc.invalidateQueries({ queryKey: ['job-counts'] })
    qc.invalidateQueries({ queryKey: ['job'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
  }
}

export function useToggleFavorite() {
  const invalidate = useInvalidateJobs()
  return useMutation({
    mutationFn: (id: string) => jobsApi.toggleFavorite(id),
    onSuccess: invalidate,
  })
}

export function useMarkApplied() {
  const invalidate = useInvalidateJobs()
  return useMutation({
    mutationFn: ({ id, applied }: { id: string; applied: boolean }) => jobsApi.markApplied(id, applied),
    onSuccess: invalidate,
  })
}

export function useMarkNotInterested() {
  const invalidate = useInvalidateJobs()
  return useMutation({
    mutationFn: (ids: string[]) => jobsApi.markNotInterested(ids),
    onSuccess: invalidate,
  })
}

export function useIgnoreJobUpdate() {
  const invalidate = useInvalidateJobs()
  return useMutation({
    mutationFn: (id: string) => jobsApi.ignoreJobUpdate(id),
    onSuccess: invalidate,
  })
}

export function useFavoriteMany() {
  const invalidate = useInvalidateJobs()
  return useMutation({
    mutationFn: (ids: string[]) => jobsApi.favoriteMany(ids),
    onSuccess: invalidate,
  })
}

export function useOfficialScreeningStatus() {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['official-screening'],
    queryFn: jobsApi.getOfficialScreeningStatus,
    refetchInterval: (q) => q.state.data?.status === 'running' ? 1500 : false,
  })
  const processed = query.data?.processed
  const status = query.data?.status
  useEffect(() => {
    if (processed !== undefined) {
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: ['job'] })
      void qc.invalidateQueries({ queryKey: ['job-counts'] })
    }
  }, [processed, status, qc])
  return query
}

export function useStartOfficialScreening() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ ids, force }: { ids?: string[]; force?: boolean }) => jobsApi.startOfficialScreening(ids, force),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['official-screening'] }),
  })
}
