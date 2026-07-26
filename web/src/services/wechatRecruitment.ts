import { apiRequest } from './config'
import type {
  WechatAccountScope,
  WechatAccountVerification,
  WechatRecruitmentAccount,
  WechatRecruitmentArticle,
  WechatRecruitmentHealth,
  WechatRecruitmentScan,
} from '@/types'

export interface WechatAccountInput {
  accountName: string
  accountIdentifier?: string
  bizId?: string
  scope: WechatAccountScope
  parentCompany?: string
  attributionKeywords: string[]
  verificationStatus: WechatAccountVerification
  enabled: boolean
}

export function getWechatHealth(): Promise<WechatRecruitmentHealth> {
  return apiRequest('/wechat-recruitment/health')
}

export function getWechatAccounts(candidateId: string): Promise<WechatRecruitmentAccount[]> {
  return apiRequest(`/company-candidates/${encodeURIComponent(candidateId)}/wechat-accounts`)
}

export function createWechatAccount(
  candidateId: string,
  input: WechatAccountInput,
): Promise<WechatRecruitmentAccount> {
  return apiRequest(`/company-candidates/${encodeURIComponent(candidateId)}/wechat-accounts`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateWechatAccount(
  candidateId: string,
  accountId: string,
  input: WechatAccountInput,
): Promise<WechatRecruitmentAccount> {
  return apiRequest(
    `/company-candidates/${encodeURIComponent(candidateId)}/wechat-accounts/${encodeURIComponent(accountId)}`,
    {
      method: 'PUT',
      body: JSON.stringify(input),
    },
  )
}

export function deleteWechatAccount(
  candidateId: string,
  accountId: string,
): Promise<{ ok: boolean }> {
  return apiRequest(
    `/company-candidates/${encodeURIComponent(candidateId)}/wechat-accounts/${encodeURIComponent(accountId)}`,
    { method: 'DELETE' },
  )
}

export function startWechatScan(candidateId: string): Promise<{ ok: boolean; scanId: string }> {
  return apiRequest(`/company-candidates/${encodeURIComponent(candidateId)}/wechat-scans`, {
    method: 'POST',
  })
}

export function getLatestWechatScan(candidateId: string): Promise<WechatRecruitmentScan | null> {
  return apiRequest(`/company-candidates/${encodeURIComponent(candidateId)}/wechat-scans/latest`)
}

export function getWechatArticles(candidateId: string): Promise<WechatRecruitmentArticle[]> {
  return apiRequest(`/company-candidates/${encodeURIComponent(candidateId)}/wechat-articles`)
}
