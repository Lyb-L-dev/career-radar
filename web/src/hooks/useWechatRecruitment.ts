import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as wechatApi from '@/services/wechatRecruitment'

export function useWechatHealth() {
  return useQuery({
    queryKey: ['wechat-recruitment', 'health'],
    queryFn: wechatApi.getWechatHealth,
    staleTime: 30_000,
  })
}

export function useWechatAccounts(candidateId: string) {
  return useQuery({
    queryKey: ['wechat-recruitment', candidateId, 'accounts'],
    queryFn: () => wechatApi.getWechatAccounts(candidateId),
  })
}

export function useSaveWechatAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      candidateId,
      accountId,
      input,
    }: {
      candidateId: string
      accountId?: string
      input: wechatApi.WechatAccountInput
    }) => accountId
      ? wechatApi.updateWechatAccount(candidateId, accountId, input)
      : wechatApi.createWechatAccount(candidateId, input),
    onSuccess: (_account, variables) => queryClient.invalidateQueries({
      queryKey: ['wechat-recruitment', variables.candidateId, 'accounts'],
    }),
  })
}

export function useDeleteWechatAccount() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      candidateId,
      accountId,
    }: {
      candidateId: string
      accountId: string
    }) => wechatApi.deleteWechatAccount(candidateId, accountId),
    onSuccess: (_result, variables) => queryClient.invalidateQueries({
      queryKey: ['wechat-recruitment', variables.candidateId, 'accounts'],
    }),
  })
}

export function useLatestWechatScan(candidateId: string) {
  return useQuery({
    queryKey: ['wechat-recruitment', candidateId, 'latest-scan'],
    queryFn: () => wechatApi.getLatestWechatScan(candidateId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 3_000 : false
    },
  })
}

export function useWechatArticles(candidateId: string) {
  return useQuery({
    queryKey: ['wechat-recruitment', candidateId, 'articles'],
    queryFn: () => wechatApi.getWechatArticles(candidateId),
  })
}

export function useStartWechatScan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: wechatApi.startWechatScan,
    onSuccess: (_result, candidateId) => {
      queryClient.invalidateQueries({
        queryKey: ['wechat-recruitment', candidateId, 'latest-scan'],
      })
      queryClient.invalidateQueries({
        queryKey: ['wechat-recruitment', candidateId, 'articles'],
      })
    },
  })
}
