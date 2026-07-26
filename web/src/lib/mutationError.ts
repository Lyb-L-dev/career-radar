import { toast } from 'sonner'

export function showMutationError(title: string, error: unknown, fallback = '请稍后重试。') {
  toast.error(title, {
    description: error instanceof Error ? error.message : fallback,
  })
}
