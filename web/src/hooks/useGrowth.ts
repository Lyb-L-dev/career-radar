import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ensureGrowthPlan, getGrowth } from '@/services/growth'

export function useGrowthOverview() {
  const client = useQueryClient()
  const attempted = useRef<string | null>(null)
  const query = useQuery({ queryKey: ['growth'], queryFn: getGrowth, refetchOnWindowFocus: true, refetchOnMount: 'always', refetchInterval: (q) => q.state.data?.operations.some((o) => ['queued', 'running'].includes(o.status)) ? 1000 : false })
  useEffect(() => {
    const data = query.data
    if (!data || data.plan || !data.nextSkillId || attempted.current === data.today) return
    if (data.operations.some((operation) => ['queued', 'running'].includes(operation.status))) return
    attempted.current = data.today
    void ensureGrowthPlan().then(() => client.invalidateQueries({ queryKey: ['growth'] })).catch(() => {
      // The explicit generation button remains available; don't loop on errors.
    })
  }, [query.data, client])
  return query
}
