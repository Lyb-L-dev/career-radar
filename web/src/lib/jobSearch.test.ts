import { describe, expect, it } from 'vitest'
import { companyMatchesKeyword, jobMatchesKeyword } from './jobSearch'

const job = {
  title: '后端开发工程师',
  companyName: '甲公司',
  city: '福州',
  jdText: '负责微服务与分布式系统，熟悉 Python。',
  tags: ['校招', '2026 届'],
}

describe('jobMatchesKeyword', () => {
  it('matches across title, company, city, jdText and tags', () => {
    expect(jobMatchesKeyword(job, '后端')).toBe(true)
    expect(jobMatchesKeyword(job, '甲公司')).toBe(true)
    expect(jobMatchesKeyword(job, '福州')).toBe(true)
    expect(jobMatchesKeyword(job, '分布式')).toBe(true)
    expect(jobMatchesKeyword(job, '2026 届')).toBe(true)
  })

  it('is case-insensitive and trims whitespace', () => {
    expect(jobMatchesKeyword(job, ' python ')).toBe(true)
    expect(jobMatchesKeyword(job, 'PYTHON')).toBe(true)
  })

  it('returns true for empty keyword and false for misses', () => {
    expect(jobMatchesKeyword(job, '')).toBe(true)
    expect(jobMatchesKeyword(job, '平面设计')).toBe(false)
  })
})

describe('companyMatchesKeyword', () => {
  const company = {
    name: '某科技公司',
    shortName: '某科',
    industry: '人工智能与数据',
    website: 'https://example.com',
  }

  it('matches name, shortName, industry and website', () => {
    expect(companyMatchesKeyword(company, '某科技')).toBe(true)
    expect(companyMatchesKeyword(company, '某科')).toBe(true)
    expect(companyMatchesKeyword(company, '人工智能')).toBe(true)
    expect(companyMatchesKeyword(company, 'example.com')).toBe(true)
  })

  it('returns true for empty keyword and false for misses', () => {
    expect(companyMatchesKeyword(company, '')).toBe(true)
    expect(companyMatchesKeyword(company, '不存在')).toBe(false)
  })
})
