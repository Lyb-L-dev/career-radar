import { describe, expect, it } from 'vitest'
import { isActiveRunStatus } from './runStatus'

describe('isActiveRunStatus', () => {
  it('keeps polling while a cooperative stop is pending', () => {
    expect(isActiveRunStatus('pending')).toBe(true)
    expect(isActiveRunStatus('running')).toBe(true)
    expect(isActiveRunStatus('stopping')).toBe(true)
  })

  it('does not poll terminal states', () => {
    expect(isActiveRunStatus('completed')).toBe(false)
    expect(isActiveRunStatus('interrupted')).toBe(false)
    expect(isActiveRunStatus('failed')).toBe(false)
  })
})
