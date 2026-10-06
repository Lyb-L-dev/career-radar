import { afterEach, describe, expect, it, vi } from 'vitest'
import { resendReportEmail } from './reports'

function response(payload: object): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response
}

describe('report email delivery', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends explicit confirmation for a real historical email', async () => {
    const result = {
      ok: true,
      message: '历史日报邮件已发送',
      eventCount: 2,
      sentAt: '2026-08-10T09:00:00+08:00',
    }
    const fetchMock = vi.fn().mockResolvedValue(response(result))
    vi.stubGlobal('fetch', fetchMock)

    await expect(resendReportEmail('2026-08-10', true)).resolves.toEqual(result)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/reports/2026-08-10/resend',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      }),
    )
  })
})
