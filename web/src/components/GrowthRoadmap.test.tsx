import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GrowthRoadmap from './GrowthRoadmap'
import { layoutGrowthSkills } from '@/lib/growthMap'
import type { GrowthSkill } from '@/services/growth'

const skill = (id: string, name: string, dependencies: string[], changes: Partial<GrowthSkill> = {}): GrowthSkill => ({
  id, name, dependencies, group: '开发基础', level: 0, highestLevel: 0, status: 'unverified', points: [],
  relevant: true, recommended: false, references: [], reason: '', selfReported: [], lastRecall: null,
  streak: 0, nextReview: null, reviewDue: false, proofIds: [], evidenceCount: 0, rubricVersion: 'test', ...changes,
})

describe('growth roadmap', () => {
  afterEach(cleanup)
  it('places prerequisites before dependent skills, independently of catalog order', () => {
    const nodes = layoutGrowthSkills([skill('api', 'API', ['http']), skill('http', 'HTTP', [])])
    expect(nodes.find((node) => node.id === 'http')!.x).toBeLessThan(nodes.find((node) => node.id === 'api')!.x)
  })

  it('exposes evidence status, review status and selection without relying on color', () => {
    const onSelect = vi.fn()
    render(<GrowthRoadmap skills={[skill('http', 'HTTP', [], { level: 3, highestLevel: 3, status: 'mastered', reviewDue: true })]} groups={['开发基础']} selected={null} onSelect={onSelect} />)
    const node = screen.getByRole('button', { name: /HTTP，等级 3，已有掌握证据，待复习/ })
    expect(within(node).getByText('待复习')).toBeVisible()
    fireEvent.click(node)
    expect(onSelect).toHaveBeenCalledWith('http')
  })

  it('keeps unassessed skills unknown and lets users expand the catalog and collapse groups', () => {
    render(<GrowthRoadmap skills={[skill('http', 'HTTP', [], { relevant: false })]} groups={['开发基础']} selected={null} onSelect={() => undefined} />)
    expect(screen.queryByRole('button', { name: /HTTP，待验证/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: '显示全部技能' }))
    expect(screen.getByRole('button', { name: /HTTP，待验证/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '开发基础' }))
    expect(screen.queryByRole('button', { name: /HTTP，待验证/ })).not.toBeInTheDocument()
  })
})
