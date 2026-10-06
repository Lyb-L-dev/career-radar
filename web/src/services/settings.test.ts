import { afterEach, describe, expect, it, vi } from 'vitest'
import { changeAutomation, deleteBackup, runMaintenance, testLlmConnection, verifyBackup } from './settings'

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

  it('sends explicit confirmation for one model connection test', async () => {
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

  it('creates a local backup through the maintenance endpoint', async () => {
    const result = {
      ok: true,
      message: '本地备份已创建',
      backupName: 'career-radar-backup-test.zip',
      includedFiles: 8,
      sizeBytes: 4096,
    }
    const fetchMock = vi.fn().mockResolvedValue(response(result))
    vi.stubGlobal('fetch', fetchMock)

    await expect(runMaintenance('export')).resolves.toEqual(result)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/maintenance/export',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('verifies and deletes one named backup with explicit confirmation', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ ok: true, integrityStatus: 'valid' }))
      .mockResolvedValueOnce(response({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    const name = 'career-radar-backup-20260810-120000-000000.zip'

    await verifyBackup(name)
    await deleteBackup(name, true)

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `/api/settings/backups/${name}/verify`,
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/settings/backups/${name}`,
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ confirmed: true }),
      }),
    )
  })
})
