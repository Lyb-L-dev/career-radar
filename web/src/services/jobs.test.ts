import { describe, expect, it } from 'vitest'
import type { Job, JobFilter } from '@/types'
import { matchFilter } from './jobs'

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    title: '后端开发工程师',
    companyId: 'c-acme',
    companyName: '甲公司',
    companyType: 'private',
    companyIndustry: 'internet',
    companyProvince: '福建',
    companyCity: '福州',
    city: '福州',
    type: 'campus',
    status: 'new',
    gradYearMatch: 'high',
    abilityMatch: 'high',
    difficulty: 6,
    isFavorite: false,
    isApplied: false,
    notInterested: false,
    hasApplyUrl: true,
    applyUrl: 'https://example.com/apply',
    sourceUrl: 'https://example.com/job/1',
    firstSeenAt: '2026-08-01T08:00:00+08:00',
    lastUpdatedAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    tags: ['校招'],
    overview: '负责核心系统开发',
    responsibilities: ['系统设计'],
    requirements: ['熟悉 Python'],
    plusPoints: [],
    locationDetail: '福州',
    applyMethod: '官网申请',
    jdText: '负责微服务与分布式系统，熟悉 Python。',
    analysis: {
      conclusion: '匹配度高',
      hasSkills: ['Python'],
      missingSkills: [],
      suggestions: [],
      advice: '建议投递',
    },
    difficultyFactors: [{ label: '竞争', level: '中', note: '岗位热门' }],
    source: {
      site: '官网',
      page: '招聘页',
      method: '官方接口',
      urlVerified: true,
      lastVerifiedAt: '2026-08-07T08:00:00+08:00',
    },
    history: [],
    ...overrides,
  } as Job
}

function filter(overrides: Partial<JobFilter> = {}): JobFilter {
  return { tab: 'all', ...overrides }
}

describe('matchFilter', () => {
  it('filters by tab: notice', () => {
    expect(matchFilter(makeJob({ type: 'notice' }), filter({ tab: 'notice' }))).toBe(true)
    expect(matchFilter(makeJob({ type: 'campus' }), filter({ tab: 'notice' }))).toBe(false)
  })

  it('filters by tab: new', () => {
    expect(matchFilter(makeJob({ status: 'new' }), filter({ tab: 'new' }))).toBe(true)
    expect(matchFilter(makeJob({ status: 'updated' }), filter({ tab: 'new' }))).toBe(false)
  })

  it('filters by tab: updated', () => {
    expect(matchFilter(makeJob({ status: 'updated' }), filter({ tab: 'updated' }))).toBe(true)
  })

  it('filters by tab: favorite', () => {
    expect(matchFilter(makeJob({ isFavorite: true }), filter({ tab: 'favorite' }))).toBe(true)
    expect(matchFilter(makeJob({ isFavorite: false }), filter({ tab: 'favorite' }))).toBe(false)
  })

  it('filters by tab: recommended', () => {
    const recommended = filter({ tab: 'recommended' })
    expect(matchFilter(makeJob({ abilityMatch: 'medium' }), recommended)).toBe(true)
    expect(matchFilter(makeJob({ abilityMatch: 'low' }), recommended)).toBe(false)
    expect(matchFilter(makeJob({ status: 'closed' }), recommended)).toBe(false)
    expect(matchFilter(makeJob({ notInterested: true }), recommended)).toBe(false)
  })

  it('filters by keyword across JD text', () => {
    expect(matchFilter(makeJob(), filter({ keyword: '分布式' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ keyword: '平面设计' }))).toBe(false)
  })

  it('filters by company, type, industry, province and city', () => {
    expect(matchFilter(makeJob(), filter({ companyId: 'c-acme' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ companyId: 'c-other' }))).toBe(false)
    expect(matchFilter(makeJob(), filter({ companyType: 'private' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ companyType: 'central_soe' }))).toBe(false)
    expect(matchFilter(makeJob(), filter({ industryCategory: 'internet' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ province: '福建' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ city: '福州' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ city: '厦门' }))).toBe(false)
  })

  it('filters by job type', () => {
    expect(matchFilter(makeJob({ type: 'campus' }), filter({ type: 'campus' }))).toBe(true)
    expect(matchFilter(makeJob({ type: 'fulltime' }), filter({ type: 'campus' }))).toBe(false)
  })

  it('filters by match levels and difficulty', () => {
    expect(matchFilter(makeJob(), filter({ gradYearMatch: 'high' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ gradYearMatch: 'low' }))).toBe(false)
    expect(matchFilter(makeJob(), filter({ abilityMatch: 'high' }))).toBe(true)
    expect(matchFilter(makeJob(), filter({ abilityMatch: 'low' }))).toBe(false)
    expect(matchFilter(makeJob({ difficulty: 8 }), filter({ difficultyMax: 7 }))).toBe(false)
    expect(matchFilter(makeJob({ difficulty: 6 }), filter({ difficultyMax: 7 }))).toBe(true)
  })

  it('filters by update recency and apply url presence', () => {
    expect(matchFilter(makeJob(), filter({ changedWithinDays: 7 }))).toBe(true)
    const stale = makeJob({ lastUpdatedAt: '2025-01-01 08:00:00' })
    expect(matchFilter(stale, filter({ changedWithinDays: 7 }))).toBe(false)
    expect(matchFilter(makeJob(), filter({ hasApplyUrl: true }))).toBe(true)
    expect(matchFilter(makeJob({ hasApplyUrl: false }), filter({ hasApplyUrl: true }))).toBe(false)
  })
})
