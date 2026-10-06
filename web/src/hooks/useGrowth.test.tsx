import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { GrowthSnapshot } from '@/services/growth'

const mocks = vi.hoisted(() => ({ data: undefined as unknown, ensure: vi.fn(), client: { invalidateQueries: vi.fn() } }))
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: mocks.data }), useQueryClient: () => mocks.client }))
vi.mock('@/services/growth', () => ({ getGrowth: vi.fn(), ensureGrowthPlan: mocks.ensure }))
import { useGrowthOverview } from './useGrowth'

function Probe() { useGrowthOverview(); return null }
function snapshot(): GrowthSnapshot {
  return { today: '2026-10-05', groups: [], levels: [], skills: [], targets: [], sampleCount: 2, sampleNotice: '目标样本', nextSkillId: 'http', plan: null, settings: { dailyMinutes: 120 }, sessions: [], operations: [] }
}

describe('daily growth planning', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.ensure.mockResolvedValue({ id: '2026-10-05' })
    mocks.client.invalidateQueries.mockResolvedValue(undefined)
  })
  afterEach(cleanup)

  it('waits for the whole background analysis before freezing a daily plan', async () => {
    const partial = snapshot()
    partial.operations = [{ id: 'analysis', kind: 'analyze', status: 'running', error: null, result: null, createdAt: '2026-10-05' }]
    mocks.data = partial
    const view = render(<Probe />)
    expect(mocks.ensure).not.toHaveBeenCalled()
    mocks.data = { ...partial, operations: [{ ...partial.operations[0], status: 'completed' }] }
    view.rerender(<Probe />)
    await waitFor(() => expect(mocks.ensure).toHaveBeenCalledTimes(1))
    view.rerender(<Probe />)
    expect(mocks.ensure).toHaveBeenCalledTimes(1)
  })

  it('keeps an existing plan stable and generates again on a new Beijing day', async () => {
    mocks.data = { ...snapshot(), plan: { id: '2026-10-05', date: '2026-10-05', tasks: [], revision: 1 } }
    const view = render(<Probe />)
    expect(mocks.ensure).not.toHaveBeenCalled()
    mocks.data = { ...snapshot(), today: '2026-10-06' }
    view.rerender(<Probe />)
    await waitFor(() => expect(mocks.ensure).toHaveBeenCalledTimes(1))
  })
})
