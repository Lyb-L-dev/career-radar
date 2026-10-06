import { Link } from 'react-router'
import { ArrowRight, CircleCheck, Map } from 'lucide-react'
import { useGrowthOverview } from '@/hooks/useGrowth'
import { addGrowthTarget } from '@/services/growth'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

export function GrowthTargetButton({ source, id, disabled = false }: { source: 'official' | 'boss'; id: string; disabled?: boolean }) {
  const client = useQueryClient()
  const mutation = useMutation({ mutationFn: () => addGrowthTarget({ source, id }), onSuccess: () => {
    void client.invalidateQueries({ queryKey: ['growth'] })
    toast.success('已加入成长目标', { description: '在成长计划中分析 JD，查看能力差距。' })
  }, onError: (error) => toast.error(error.message) })
  return <Button size="sm" variant="outline" disabled={disabled || mutation.isPending} onClick={() => mutation.mutate()}><Map className="size-4" />{mutation.isPending ? '正在加入…' : '加入成长目标'}</Button>
}

export default function GrowthSummary() {
  const query = useGrowthOverview()
  return <section className="rounded-xl bg-surface p-5" aria-labelledby="growth-summary-title">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="growth-summary-title" className="text-lg font-semibold text-ink">今天，留下两份能力证据</h2><Link to="/growth" className="inline-flex shrink-0 items-center gap-1 text-sm text-brand-foreground hover:underline">成长计划 <ArrowRight className="size-4" /></Link></div>
    {query.isPending ? <p className="mt-3 text-sm text-ink-secondary">正在读取今日任务…</p> : query.isError && !query.data ? <div className="mt-3 text-sm text-ink-secondary">成长计划加载失败。<button onClick={() => void query.refetch()} className="ml-2 text-brand-foreground underline">重试</button></div> : query.data.plan ? <div className="mt-3 grid gap-3 md:grid-cols-2">{query.data.plan.tasks.map((task) => <Link key={task.id} to={`/growth?tab=today&skill=${task.skillId}`} className="flex items-start gap-3 rounded-lg p-2 hover:bg-black/[0.03]"><CircleCheck className={`mt-0.5 size-5 shrink-0 ${task.status === 'done' ? 'text-success' : 'text-ink-secondary'}`} /><span><span className="block text-xs text-ink-secondary">{task.kind === 'learning' ? '学习 · 主动回忆' : '项目 · 实践证据'}</span><span className="mt-1 block text-sm font-medium text-ink">{task.title}</span></span></Link>)}</div> : <p className="mt-3 text-sm text-ink-secondary">选择目标 JD，系统会把岗位要求变成测评与今日行动。<Link to="/growth?tab=targets" className="ml-2 text-brand-foreground underline">选择岗位</Link></p>}
  </section>
}
