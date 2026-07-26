import { describe, expect, it } from 'vitest'
import { pollingInterval } from './polling'

describe('pollingInterval', () => {
  it('polls only while the resource is active', () => {
    expect(pollingInterval(true, false, 3_000)).toBe(3_000)
    expect(pollingInterval(false, false, 3_000)).toBe(false)
  })

  it('backs off after an error', () => {
    expect(pollingInterval(true, true, 3_000)).toBe(15_000)
    expect(pollingInterval(false, true, 3_000)).toBe(15_000)
  })
})
