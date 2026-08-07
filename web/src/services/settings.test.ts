import { afterEach, describe, expect, it, vi } from 'vitest'
import { changeAutomation, testLlmConnection } from './settings'

function response(payload: object): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response
}

describe('paid and system-changing settings actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends explicit confirmation when installing automation', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ installed: true }))
    vi.stubGlobal('fetch', fetchMock)

    await changeAutomation('install', '08:15')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/automation/install',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ confirmed: true, dailyRunTime: '08:15' }),
      }),
    )
  })

  it('sends explicit confirmation for one DeepSeek connection test', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    await testLlmConnection(true)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/test-llm',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      }),
    )
  })
})
