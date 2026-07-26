import { apiRequest, delay, copy, USE_MOCK } from './config'
import { companies } from '@/mocks/companies'
import type { Company, CompanyError, CompanyPageRecord, CompanyPriority, CompanyTestResult, IndustryCategory, MonitorMode } from '@/types'

export async function getCompanies(): Promise<Company[]> {
  if (!USE_MOCK) return apiRequest('/companies')
  return delay(copy(companies))
}

export async function getCompany(id: string): Promise<Company | undefined> {
  if (!USE_MOCK) return apiRequest(`/companies/${encodeURIComponent(id)}`)
  return delay(copy(companies.find((c) => c.id === id)))
}

export interface NewCompanyInput {
  name: string
  website: string
  careersUrl?: string
  companyType: Company['companyType']
  industryCategory?: IndustryCategory
  province?: string
  city?: string
  priority?: CompanyPriority
  monitorMode?: MonitorMode
  renderMode: Company['renderMode']
  maxPages: number
  enabled: boolean
  note?: string
}

export async function addCompany(input: NewCompanyInput): Promise<Company> {
  if (!USE_MOCK) {
    return apiRequest('/companies', { method: 'POST', body: JSON.stringify(input) })
  }
  const company: Company = {
    id: `c-${Date.now()}`,
    name: input.name,
    shortName: input.name.split(' ')[0] ?? input.name,
    website: input.website,
    careersUrl: input.careersUrl || undefined,
    industry: '待补充',
    industryCategory: input.industryCategory ?? 'other',
    companyType: input.companyType,
    province: input.province,
    city: input.city,
    priority: input.priority ?? 'medium',
    monitorMode: input.monitorMode ?? 'jobs',
    governmentHonors: [],
    evidenceUrls: [],
    status: 'pending_verification',
    renderMode: input.renderMode,
    robotsStatus: 'unknown',
    recentJobCount: 0,
    consecutiveFailures: 0,
    maxPages: input.maxPages,
    enabled: input.enabled,
    note: input.note,
    addedAt: new Date().toISOString().slice(0, 16).replace('T', ' '),
  }
  companies.unshift(company)
  return delay(copy(company), 300, 500)
}

export async function updateCompany(id: string, patch: Partial<Company>): Promise<{ ok: boolean }> {
  if (!USE_MOCK) {
    return apiRequest(`/companies/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  }
  const c = companies.find((x) => x.id === id)
  if (c) Object.assign(c, patch)
  return delay({ ok: true }, 200, 400)
}

export async function removeCompany(id: string): Promise<{ ok: boolean }> {
  if (!USE_MOCK) return apiRequest(`/companies/${encodeURIComponent(id)}`, { method: 'DELETE' })
  const idx = companies.findIndex((x) => x.id === id)
  if (idx >= 0) companies.splice(idx, 1)
  return delay({ ok: true }, 200, 400)
}

export async function removeCompanies(ids: string[]): Promise<{ ok: boolean; deleted: number }> {
  if (!USE_MOCK) {
    return apiRequest('/companies/bulk-delete', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
  }
  const selected = new Set(ids)
  const deletable = companies.filter((company) => selected.has(company.id)).length
  if (companies.length - deletable < 1) {
    throw new Error('至少保留一家企业配置')
  }
  for (let index = companies.length - 1; index >= 0; index -= 1) {
    if (selected.has(companies[index].id)) companies.splice(index, 1)
  }
  return delay({ ok: true, deleted: deletable }, 200, 400)
}

export async function testCompanyConnection(_website: string, _careersUrl?: string): Promise<CompanyTestResult> {
  if (!USE_MOCK) {
    return apiRequest('/companies/test', {
      method: 'POST',
      body: JSON.stringify({ website: _website, careersUrl: _careersUrl }),
    })
  }
  // 模拟真实探测耗时更长
  return delay(
    {
      robotsAllowed: true,
      homepageReachable: true,
      entryFound: true,
      entryUrl: _careersUrl || `${_website.replace(/\/$/, '')}/careers`,
      needsBrowserRender: false,
      estimatedPages: 12,
    },
    900,
    1500,
  )
}

const pageRecords: Record<string, CompanyPageRecord[]> = {
  'c-fit2cloud': [
    { url: 'https://fit2cloud.com/', pageType: '首页', method: 'requests', httpStatus: 200, contentLength: 48210, llmExtracted: false, fetchedAt: '2026-07-18 09:41:04' },
    { url: 'https://fit2cloud.com/careers/', pageType: '招聘列表页', method: 'requests', httpStatus: 200, contentLength: 31240, llmExtracted: false, fetchedAt: '2026-07-18 09:41:06' },
    { url: 'https://fit2cloud.com/careers/ai-agent-engineer-intern', pageType: '职位详情页', method: 'requests', httpStatus: 200, contentLength: 12880, llmExtracted: true, fetchedAt: '2026-07-18 09:41:09' },
    { url: 'https://fit2cloud.com/careers/training-center-intern', pageType: '职位详情页', method: 'requests', httpStatus: 200, contentLength: 9410, llmExtracted: true, fetchedAt: '2026-07-18 09:41:12' },
    { url: 'https://fit2cloud.com/careers/ai-content-operation-intern', pageType: '职位详情页', method: 'requests', httpStatus: 200, contentLength: 8760, llmExtracted: true, fetchedAt: '2026-07-18 09:41:15' },
  ],
  'c-smartx': [
    { url: 'https://www.smartx.com/', pageType: '首页', method: 'playwright', httpStatus: 200, contentLength: 66420, llmExtracted: false, fetchedAt: '2026-07-18 09:42:29' },
    { url: 'https://www.smartx.com/careers', pageType: '招聘列表页', method: 'playwright', httpStatus: 403, contentLength: 1210, llmExtracted: false, fetchedAt: '2026-07-18 09:42:30' },
  ],
}

const companyErrors: Record<string, CompanyError[]> = {
  'c-smartx': [
    {
      time: '2026-07-18 09:42:30',
      message: '页面返回 403，系统按照合规策略未继续尝试。该问题已连续出现 2 次，已暂停自动重试。',
      technicalDetail:
        'GET https://www.smartx.com/careers -> HTTP 403 Forbidden\nServer: cloudflare\nCF-RAY: 8f2c1e...\nplaywright 渲染后正文长度 1210 字符，低于最低阈值 500 字节的拦截页特征。\n策略：连续失败 2 次，进入冷却期，下次运行不再自动重试。',
    },
    {
      time: '2026-07-17 09:31:02',
      message: '页面返回 403，系统按照合规策略未继续尝试。',
      technicalDetail: 'GET https://www.smartx.com/careers -> HTTP 403 Forbidden\n首次出现，已记录并继续其他企业。',
    },
  ],
  'c-nebula': [
    {
      time: '2026-07-18 09:42:31',
      message: 'robots.txt 禁止抓取招聘路径，系统已停止访问该站点。',
      technicalDetail:
        'GET https://nebula-graph.com.cn/robots.txt -> HTTP 200\nUser-agent: *\nDisallow: /careers\nDisallow: /join\n解析结果：招聘路径被明确禁止，按合规策略跳过。',
    },
  ],
}

export async function getCompanyPageRecords(companyId: string): Promise<CompanyPageRecord[]> {
  if (!USE_MOCK) return apiRequest(`/companies/${encodeURIComponent(companyId)}/pages`)
  return delay(copy(pageRecords[companyId] ?? []))
}

export async function getCompanyErrors(companyId: string): Promise<CompanyError[]> {
  if (!USE_MOCK) return apiRequest(`/companies/${encodeURIComponent(companyId)}/errors`)
  return delay(copy(companyErrors[companyId] ?? []))
}
