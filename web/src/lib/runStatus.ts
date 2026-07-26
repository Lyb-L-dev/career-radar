import type { RunStatus } from '@/types'

export function isActiveRunStatus(status: RunStatus): boolean {
  return status === 'pending' || status === 'running' || status === 'stopping'
}
