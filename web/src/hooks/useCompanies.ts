import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as companiesApi from '@/services/companies'
import type { Company } from '@/types'
import { pollingInterval } from '@/lib/polling'

export function useCompanies() {
  return useQuery({ queryKey: ['companies'], queryFn: companiesApi.getCompanies })
}

export function useCompany(id: string) {
  return useQuery({ queryKey: ['company', id], queryFn: () => companiesApi.getCompany(id) })
}

export function useCompanyPageRecords(id: string, scanning: boolean) {
  return useQuery({
    queryKey: ['company-pages', id],
    queryFn: () => companiesApi.getCompanyPageRecords(id),
    enabled: Boolean(id),
    staleTime: scanning ? 0 : 30_000,
    refetchInterval: (query) =>
      pollingInterval(scanning, Boolean(query.state.error), 5_000),
  })
}

export function useCompanyErrors(id: string) {
  return useQuery({
    queryKey: ['company-errors', id],
    queryFn: () => companiesApi.getCompanyErrors(id),
    staleTime: 30_000,
  })
}

export function useAddCompany() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: companiesApi.NewCompanyInput) => companiesApi.addCompany(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companies'] }),
  })
}

export function useUpdateCompany() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Company> }) => companiesApi.updateCompany(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['companies'] })
      qc.invalidateQueries({ queryKey: ['company'] })
    },
  })
}

export function useRemoveCompany() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => companiesApi.removeCompany(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['companies'] }),
  })
}

export function useRemoveCompanies() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => companiesApi.removeCompanies(ids),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['companies'] })
      qc.invalidateQueries({ queryKey: ['company'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}
