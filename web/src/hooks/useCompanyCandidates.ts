import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as candidatesApi from '@/services/companyCandidates'

export function useCompanyCandidates(filters: candidatesApi.CandidateFilters) {
  return useQuery({
    queryKey: ['company-candidates', filters],
    queryFn: () => candidatesApi.getCompanyCandidates(filters),
    placeholderData: (previous) => previous,
  })
}

export function useReviewCompanyCandidate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: candidatesApi.CandidateReviewInput }) =>
      candidatesApi.reviewCompanyCandidate(id, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['company-candidates'] }),
  })
}

export function useDiscoverCompanyWebsite() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => candidatesApi.discoverCompanyWebsite(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['company-candidates'] }),
  })
}

export function useMonitorCompanyCandidate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: candidatesApi.CandidateMonitorInput }) =>
      candidatesApi.monitorCompanyCandidate(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-candidates'] })
      queryClient.invalidateQueries({ queryKey: ['companies'] })
    },
  })
}

export function useCandidateSources(id: string) {
  return useQuery({
    queryKey: ['company-candidates', id, 'sources'],
    queryFn: () => candidatesApi.getCandidateSources(id),
  })
}

export function useAddCandidateSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: candidatesApi.CandidateSourceInput }) =>
      candidatesApi.addCandidateSource(id, input),
    onSuccess: (_source, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['company-candidates', variables.id, 'sources'],
      })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
