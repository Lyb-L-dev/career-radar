import type { Job, Company } from '@/types'

/**
 * 岗位与公司的关键字匹配，统一供岗位列表筛选、命令面板与全局搜索使用。
 * 以前三处实现不一致（命令面板漏查 JD 正文），这里收敛为单一事实来源。
 */

export function jobMatchesKeyword(
  job: Pick<Job, 'title' | 'companyName' | 'city' | 'jdText' | 'tags'>,
  keyword: string,
): boolean {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return true
  const hay = [job.title, job.companyName, job.city, job.jdText, ...job.tags]
    .join(' ')
    .toLowerCase()
  return hay.includes(kw)
}

export function companyMatchesKeyword(
  company: Pick<Company, 'name' | 'shortName' | 'industry' | 'website'>,
  keyword: string,
): boolean {
  const kw = keyword.trim().toLowerCase()
  if (!kw) return true
  const hay = [company.name, company.shortName, company.industry, company.website]
    .join(' ')
    .toLowerCase()
  return hay.includes(kw)
}
