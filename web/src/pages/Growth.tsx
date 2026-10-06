import { useLocalDraft } from '@/hooks/useBrowserState'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BookOpen, CheckCircle2, Code2, Plus, RotateCcw, Star, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ErrorState, PageSkeleton } from '@/components/common/StateViews'
import GrowthRoadmap from '@/components/GrowthRoadmap'
import GrowthEvidence from '@/components/GrowthEvidence'
import GrowthSession from '@/components/GrowthSession'
import { useGrowthOverview } from '@/hooks/useGrowth'
import { addGrowthTarget, analyzeGrowth, ensureGrowthPlan, getGrowthHistory, getGrowthOperation, getGrowthSources, reflectGrowthTask, refreshGrowthTarget, retryGrowthOperation, saveGrowthSettings, startGrowthSession, updateGrowthTarget } from '@/services/growth'
import type { GrowthOperation, GrowthSnapshot, GrowthTarget, GrowthTask } from '@/services/growth'

const TABS = [{ id: 'map', name: '能力路线图' }, { id: 'today', name: '今日行动' }, { id: 'jobs', name: 'JD 对照' }, { id: 'targets', name: '目标岗位' }, { id: 'history', name: '复盘与设置' }]
const SOURCE_NAMES = { official: '企业招聘页', boss: 'BOSS 平台线索', manual: '手动 JD' }
const TASK_STATUS = { todo: '未完成', partial: '部分完成', done: '已完成', blocked: '遇到卡点' }
const REQUIREMENT_STATUS = { qualification: '报名条件单独核对', stale: 'JD 已变化，待重新分析', unverified: '尚无独立证据', gap: '需要补齐', supported: '已有对应证据' }

function TaskView({ task, date, skills, busy, onSkill, onTarget, onOperation, onAction }: {
  task: GrowthTask; date: string; skills: GrowthSnapshot['skills']; busy: boolean; onSkill: (id: string) => void; onTarget: (id: string) => void
  onOperation: (promise: Promise<GrowthOperation>) => void; onAction: (promise: Promise<unknown>) => void
}) {
  const draft = useLocalDraft(`career-growth-task:${date}:${task.id}`, { status: task.status as string, blocker: task.blocker, output: task.output })
  const { status, blocker, output } = draft.value
  const setStatus = (value: string) => draft.update({ status: value })
  const setBlocker = (value: string) => draft.update({ blocker: value })
  const setOutput = (value: string) => draft.update({ output: value })
  return <article className="min-w-0 rounded-xl bg-surface p-5 md:p-6">
    <h2 className="text-xl font-semibold text-ink">{task.title}</h2>
    <div className="mt-2 flex items-center gap-2 text-sm text-ink-secondary">{task.kind === 'learning' ? <BookOpen className="size-4" /> : <Code2 className="size-4" />}{task.kind === 'learning' ? '学习 · 主动回忆' : '项目 · 实践证据'}{task.status === 'done' && <CheckCircle2 className="ml-auto size-5 text-success" />}</div><p className="mt-3 text-sm leading-7 text-ink-body">{task.description}</p>
    <p className="mt-4 text-sm leading-6 text-ink-secondary">为什么今天做：{task.reason}</p>
    <h3 className="mt-5 text-sm font-semibold text-ink">完成后留下什么</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-ink-body">{task.criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}</ul>
    {task.references.length > 0 && <details className="mt-4 text-sm"><summary className="cursor-pointer text-ink-secondary">查看关联的岗位原文</summary><div className="mt-2 space-y-3">{task.references.map((ref) => <button key={`${ref.targetId}-${ref.requirementId}`} type="button" className="block text-left text-brand-foreground hover:underline" onClick={() => onTarget(ref.targetId)}>{ref.title}<span className="mt-1 block text-xs leading-5 text-ink-secondary">“{ref.quote}”</span></button>)}</div></details>}
    <div className="mt-5 flex flex-wrap gap-2"><Button disabled={busy} onClick={() => task.kind === 'learning' ? onOperation(startGrowthSession([task.skillId])) : onSkill(task.skillId)}>{task.kind === 'learning' ? '开始回忆' : '查看技能并提交项目证据'}<ArrowRight className="size-4" /></Button></div>
    {task.reviewSkillIds.length > 0 && <div className="mt-4"><p className="text-xs text-ink-secondary">今天安排的变式复习</p><div className="mt-1 flex flex-wrap gap-2">{task.reviewSkillIds.map((id) => <Button key={id} size="sm" variant="ghost" disabled={busy} onClick={() => onOperation(startGrowthSession([id]))}><RotateCcw className="size-3.5" />{skills.find((s) => s.id === id)?.name}</Button>)}</div></div>}
    <details className="mt-6" open={task.status === 'blocked' || Boolean(blocker) ? true : undefined}><summary className="cursor-pointer text-sm font-medium text-brand-foreground">记录完成情况与卡点</summary><form className="mt-3 space-y-3 border-t border-black/[0.06] pt-4" onSubmit={(event) => { event.preventDefault(); onAction(reflectGrowthTask(date, { ...task, status: status as GrowthTask['status'], blocker, output }).then(result => { draft.clear(); return result })) }}>
      <label className="block text-sm text-ink">完成情况<select aria-label="完成情况" value={status} disabled={busy} onChange={(e) => setStatus(e.target.value as GrowthTask['status'])} className="mt-1 block min-h-10 w-full rounded-lg border border-black/15 bg-white px-3">{Object.entries(TASK_STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label className="block text-sm text-ink">留下的产出<Textarea aria-label="留下的产出" className="mt-1" value={output} onChange={(e) => setOutput(e.target.value)} rows={2} maxLength={5000} placeholder="回答、代码或测试记录的说明" /></label>
      <label className="block text-sm text-ink">卡在哪里<Textarea aria-label="卡在哪里" className="mt-1" value={blocker} onChange={(e) => setBlocker(e.target.value)} rows={2} maxLength={2000} placeholder="具体哪个概念或步骤不清楚？" /></label>
      <Button variant="outline" type="submit" disabled={busy}>保存反馈</Button><p className="text-xs leading-5 text-ink-secondary">完成状态用于调整明日任务；能力证据由答题和项目审阅更新。</p>
    </form></details>
  </article>
}

function Targets({ targets, busy, onAction, onOperation }: { targets: GrowthTarget[]; busy: boolean; onAction: (promise: Promise<unknown>) => void; onOperation: (promise: Promise<GrowthOperation>) => void }) {
  const sources = useQuery({ queryKey: ['growth', 'sources'], queryFn: getGrowthSources })
  const [search, setSearch] = useState('')
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [description, setDescription] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [editedDescription, setEditedDescription] = useState('')
  const visible = sources.data?.filter((s) => `${s.title} ${s.company}`.toLowerCase().includes(search.toLowerCase())) ?? []
  return <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
    <section className="min-w-0 rounded-xl bg-surface p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold text-ink">我的目标岗位组</h2><Button disabled={busy || !targets.length} onClick={() => onOperation(analyzeGrowth())}>分析岗位要求</Button></div><p className="mt-2 text-sm leading-6 text-ink-secondary">标记最多 3 条重点 JD。先用完整岗位要求，确定能力地图该关注什么。</p>
      {!targets.length && <p className="py-8 text-sm text-ink-secondary">从右侧选择岗位，或粘贴你希望争取的 JD。</p>}
      <ul className="mt-4 divide-y divide-black/[0.06]">{targets.map((target) => <li key={target.id} className="py-4"><div className="flex items-start gap-3"><div className="min-w-0 flex-1"><h3 className="font-semibold text-ink">{target.title}</h3><p className="mt-1 text-xs text-ink-secondary">{target.company || '未填企业'} · {SOURCE_NAMES[target.source]}</p><p className="mt-1 text-xs text-ink-secondary">{target.analysisStale ? '待分析 / JD 已更新' : `已提取 ${target.requirements.length} 项要求`}{target.analyzedAt && ` · ${target.analyzedAt.slice(0, 10)}`}</p></div><Button size="icon" variant="ghost" aria-label={`${target.focus ? '取消' : '标记'}重点：${target.title}`} aria-pressed={target.focus} disabled={busy} onClick={() => onAction(updateGrowthTarget(target.id, { focus: !target.focus }))}><Star className={`size-4 ${target.focus ? 'fill-amber-500 text-amber-700' : 'text-ink-secondary'}`} /></Button><Button size="icon" variant="ghost" aria-label={`移除目标：${target.title}`} disabled={busy} onClick={() => onAction(updateGrowthTarget(target.id, { active: false }))}><Trash2 className="size-4" /></Button></div><details className="mt-3 text-sm"><summary className="cursor-pointer text-ink-secondary">查看保存的 JD</summary><p className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-sm leading-7 text-ink-body">{target.description}</p></details><div className="mt-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={busy} onClick={() => onOperation(analyzeGrowth([target.id]))}>分析此 JD</Button>{target.source !== 'manual' ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => onAction(refreshGrowthTarget(target.id))}>同步最新 JD</Button> : <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setEditing(target.id); setEditedDescription(target.description) }}>修改 JD</Button>}{target.url && /^https?:\/\//.test(target.url) && <a className="inline-flex min-h-9 items-center text-sm text-brand-foreground underline" href={target.url} target="_blank" rel="noreferrer">岗位原文</a>}</div>{editing === target.id && <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); onAction(updateGrowthTarget(target.id, { description: editedDescription })); setEditing(null) }}><label className="block text-sm">完整 JD<Textarea aria-label="修改后的完整 JD" value={editedDescription} onChange={(e) => setEditedDescription(e.target.value)} rows={6} required maxLength={100000} /></label><Button type="submit" size="sm" disabled={busy}>保存 JD</Button></form>}</li>)}</ul>
    </section>
    <div className="min-w-0 space-y-6"><section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold text-ink">从现有岗位选择</h2><label className="mt-3 block text-sm text-ink">搜索岗位或企业<Input className="mt-1" value={search} onChange={(e) => setSearch(e.target.value)} /></label>{sources.isPending ? <p className="mt-4 text-sm text-ink-secondary">正在读取岗位库…</p> : sources.isError ? <div className="mt-4"><p className="text-sm text-danger">岗位库读取失败。</p><Button variant="outline" onClick={() => void sources.refetch()}>重试</Button></div> : <ul className="mt-3 max-h-80 divide-y divide-black/[0.06] overflow-auto">{visible.map((source) => { const added = targets.some((t) => t.source === source.source && t.sourceId === source.id); return <li key={`${source.source}-${source.id}`} className="flex items-center gap-3 py-3"><div className="min-w-0 flex-1"><p className="text-sm font-medium text-ink">{source.title}</p><p className="mt-1 text-xs text-ink-secondary">{source.company} · {SOURCE_NAMES[source.source]}</p></div><Button size="sm" variant="outline" disabled={busy || added || !source.jdComplete} onClick={() => onAction(addGrowthTarget({ source: source.source, id: source.id }))}>{added ? '已加入' : <><Plus className="size-3.5" />加入</>}</Button></li> })}{!visible.length && <li className="py-5 text-sm text-ink-secondary">{sources.data?.length ? '没有符合搜索条件的岗位。' : '岗位库暂时没有完整 JD，可以先粘贴一条。'}</li>}</ul>}</section>
      <form className="space-y-3 rounded-xl bg-surface p-5" onSubmit={(e) => { e.preventDefault(); onAction(addGrowthTarget({ source: 'manual', title, company, description })) }}><h2 className="text-lg font-semibold text-ink">粘贴目标 JD</h2><label className="block text-sm text-ink">岗位名称<Input className="mt-1" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} /></label><label className="block text-sm text-ink">企业名称（选填）<Input className="mt-1" value={company} onChange={(e) => setCompany(e.target.value)} maxLength={200} /></label><label className="block text-sm text-ink">完整 JD<Textarea aria-label="完整 JD" className="mt-1" value={description} onChange={(e) => setDescription(e.target.value)} rows={7} required maxLength={100000} /></label><Button type="submit" disabled={busy || !title.trim() || !description.trim()}>加入目标岗位组</Button><p className="text-xs text-ink-secondary">手动 JD 保留来源标记，分析结果限定为这些目标岗位。</p></form>
    </div>
  </div>
}

function History({ minutes, busy, onAction, onSkill }: { minutes: number; busy: boolean; onAction: (promise: Promise<unknown>) => void; onSkill: (id: string) => void }) {
  const history = useQuery({ queryKey: ['growth', 'history'], queryFn: getGrowthHistory })
  const [budget, setBudget] = useState(minutes)
  return <div className="space-y-6"><form className="max-w-lg space-y-3 rounded-xl bg-surface p-5" onSubmit={(e) => { e.preventDefault(); onAction(saveGrowthSettings(budget)) }}><h2 className="text-lg font-semibold text-ink">任务预算</h2><p className="text-sm leading-6 text-ink-secondary">预算只用于控制每日任务量。到期复习安排在学习任务内，最多占 15 分钟。</p><label className="block text-sm text-ink">每天可用分钟<Input type="number" min={30} max={480} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="mt-1" required /></label><Button type="submit" variant="outline" disabled={busy}>保存预算</Button></form><section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold text-ink">历史行动与卡点</h2>{history.isPending ? <p className="mt-4 text-sm">正在读取复盘…</p> : history.isError ? <Button className="mt-4" onClick={() => void history.refetch()}>重试读取复盘</Button> : !history.data.length ? <p className="mt-4 text-sm text-ink-secondary">保存第一天的任务反馈后，这里会留下你的推进过程。</p> : history.data.map((plan) => <section key={plan.id} className="mt-5 border-t border-black/[0.06] pt-4"><h3 className="font-semibold text-ink">{plan.date}</h3><ul className="mt-2 space-y-4">{plan.tasks.map((task) => <li key={task.id}><button onClick={() => onSkill(task.skillId)} className="text-left text-sm font-medium text-brand-foreground hover:underline">{task.title}</button><span className="ml-2 text-xs text-ink-secondary">{TASK_STATUS[task.status]}</span>{task.output && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-body">产出：{task.output}</p>}{task.blocker && <p className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-secondary">卡点：{task.blocker}</p>}</li>)}</ul></section>)}</section></div>
}

export default function GrowthPage() {
  const query = useGrowthOverview()
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [writing, setWriting] = useState(false)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<string[]>([])
  const handled = useRef<string | null>(null)
  const operation = useQuery({ queryKey: ['growth', 'operation', operationId], queryFn: () => getGrowthOperation(operationId!), enabled: Boolean(operationId), refetchInterval: (q) => ['queued', 'running'].includes(q.state.data?.status ?? 'queued') ? 1000 : false })
  const tab = TABS.some((t) => t.id === params.get('tab')) ? params.get('tab')! : 'map'
  const selected = params.get('skill')
  const sessionId = params.get('session')
  const setView = (view: string, extras: Record<string, string> = {}) => setParams({ tab: view, ...extras })
  const onSkill = (id: string) => setView('map', { skill: id })
  const onTarget = (id: string) => setView('jobs', { target: id })
  const invalidate = () => client.invalidateQueries({ queryKey: ['growth'] })
  const onAction = (promise: Promise<unknown>) => {
    setWriting(true)
    void promise.then(() => { void invalidate(); toast.success('已保存') }).catch((error: Error) => toast.error(error.message)).finally(() => setWriting(false))
  }
  const onOperation = (promise: Promise<GrowthOperation>) => {
    setWriting(true)
    void promise.then((value) => { handled.current = null; setOperationId(value.id); void invalidate() }).catch((error: Error) => toast.error(error.message)).finally(() => setWriting(false))
  }
  useEffect(() => {
    const value = operation.data
    if (!value || !['completed', 'failed'].includes(value.status) || handled.current === value.id) return
    handled.current = value.id
    void client.invalidateQueries({ queryKey: ['growth'] })
    if (value.status === 'completed' && value.result?.sessionId) {
      setParams((old) => { const updated = new URLSearchParams(old); updated.set('session', value.result!.sessionId!); return updated })
    }
    if (value.status === 'completed') toast.success(value.kind === 'analyze' ? '岗位要求分析完成' : value.kind === 'question' || value.kind === 'baseline' ? '题目已准备好' : value.kind === 'hint' ? '讲解已准备好' : '本次处理已完成')
  }, [operation.data, client, setParams])
  if (query.isPending) return <PageSkeleton />
  if (query.isError && !query.data) return <ErrorState description="成长数据读取失败，请检查本地服务后重试。" onRetry={() => void query.refetch()} />
  const data = query.data
  const pending = data.operations.some((o) => ['queued', 'running'].includes(o.status))
  const busy = writing || pending || Boolean(operationId && (!operation.data || ['queued', 'running'].includes(operation.data.status)))
  const notices = data.operations.filter((o) => o.status !== 'completed' && !dismissed.includes(o.id)).slice(-3)
  const selectedTarget = data.targets.find((t) => t.id === params.get('target'))
  const activeTargets = data.targets.filter((t) => t.active)
  const targets = selectedTarget ? [selectedTarget] : activeTargets
  return <div className="growth-surface space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-[28px] font-semibold tracking-tight text-ink">把“我学过”变成“我能证明”</h1><p className="mt-2 text-sm leading-6 text-ink-secondary">今天补一块差距，留下可以回看的回答与项目证据。</p></div><Button variant="outline" disabled={busy || !data.nextSkillId} onClick={() => onOperation(startGrowthSession([], 'baseline'))}>初次能力短测</Button></header>
    <nav className="flex flex-wrap gap-1 border-b border-black/[0.08] pb-2" aria-label="成长计划视图">{TABS.map((item) => <button key={item.id} aria-current={tab === item.id && !sessionId ? 'page' : undefined} onClick={() => setView(item.id)} className={`min-h-11 rounded-lg px-3 text-sm font-medium transition-colors ${tab === item.id ? 'bg-brand-soft text-brand-foreground' : 'text-ink-secondary hover:bg-black/[0.04]'}`}>{item.name}</button>)}</nav>
    {notices.map((notice) => <div key={notice.id} role="status" className={`flex flex-wrap items-center gap-3 rounded-lg p-4 text-sm ${notice.status === 'failed' ? 'bg-amber-50 text-amber-950' : 'bg-brand-soft text-ink'}`}><p className="min-w-0 flex-1 break-words">{notice.status === 'failed' ? notice.error : notice.status === 'queued' ? '成长任务已保存，正在等待模型资源。' : '模型正在处理，输入与进度保存在本机。'}</p>{notice.status === 'failed' && <><Button size="sm" variant="outline" disabled={busy} onClick={() => onOperation(retryGrowthOperation(notice.id))}>重试</Button><Button size="sm" variant="ghost" onClick={() => setDismissed((old) => [...old, notice.id])}>收起</Button></>}</div>)}
    {query.isError && <p role="status" className="text-sm text-danger">刷新失败，保留上次成长记录。<Button variant="ghost" onClick={() => void query.refetch()}>重试</Button></p>}
    {sessionId ? <GrowthSession key={sessionId} sessionId={sessionId} skills={data.skills} busy={busy} onOperation={onOperation} onClose={() => setParams(old => { const next = new URLSearchParams(old); next.delete('session'); return next })} onEvidence={() => setView('map', selected ? { skill: selected } : {})} /> : <>
      {tab === 'map' && <>
        {!activeTargets.length ? <section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold">从一个目标岗位开始</h2><p className="mt-2 text-sm text-ink-secondary">选择一条 JD，查看岗位要求、能力差距和今天的下一步。</p><Button className="mt-3" onClick={() => setView('targets')}>选择目标 JD</Button></section>
          : activeTargets.some(target => target.analysisStale) ? <section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold">先分析目标岗位要求</h2><p className="mt-2 text-sm text-ink-secondary">未分析或已变化的 JD 需要更新，才能安排有依据的任务。</p><Button className="mt-3" disabled={busy} onClick={() => onOperation(analyzeGrowth(activeTargets.filter(target => target.analysisStale).map(target => target.id)))}>分析目标 JD</Button></section>
          : data.sessions.some(session => session.status === 'active') ? <section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold">继续上次的测评</h2><Button className="mt-3" onClick={() => setView('map', { session: data.sessions.filter(session => session.status === 'active').at(-1)!.id })}>继续回答</Button></section>
          : !data.skills.some(skill => skill.level > 0) && <section className="rounded-xl bg-surface p-5"><h2 className="text-lg font-semibold">用第一次短测建立能力证据</h2><Button className="mt-3" disabled={busy || !data.nextSkillId} onClick={() => onOperation(startGrowthSession([], 'baseline'))}>开始能力短测</Button></section>}
        {data.plan && <section className="rounded-xl bg-surface p-5" aria-label="路线图今日行动"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-semibold">今日两项行动</h2><Link to="/growth?tab=today" className="text-sm text-brand-foreground hover:underline">查看任务与完成标准 →</Link></div><ul className="mt-3 grid gap-3 md:grid-cols-2">{data.plan.tasks.map(task => <li key={task.id}><Link to={`/growth?tab=today&skill=${task.skillId}`} className="block text-sm text-ink hover:text-brand-foreground">{task.title}<span className="mt-1 block text-xs text-ink-secondary">{task.kind === 'learning' ? '学习' : '项目'} · {TASK_STATUS[task.status]}</span></Link></li>)}</ul></section>}
        <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-ink-secondary">{data.sampleCount} 个去重目标样本 · 点击技能查看证据</p><Button variant="ghost" onClick={() => setView('targets')}>管理目标岗位 <ArrowRight className="size-4" /></Button></div><div className={`grid items-start gap-5 ${selected ? 'xl:grid-cols-[minmax(0,1fr)_360px]' : ''}`}><div className={`min-w-0 rounded-xl bg-surface p-4 md:p-5 ${selected ? 'hidden md:block' : ''}`}><GrowthRoadmap skills={data.skills} groups={data.groups} selected={selected} onSelect={onSkill} /></div>{selected && <GrowthEvidence key={selected} skillId={selected} highlighted={params.get('evidence')} levels={data.levels} busy={busy} onClose={() => setView('map')} onOperation={onOperation} onAction={onAction} onTarget={onTarget} />}</div><p className="text-xs leading-5 text-ink-secondary">{data.sampleNotice}</p>{data.sessions.some((s) => s.status === 'active') && <section className="rounded-xl bg-surface p-5"><h2 className="text-base font-semibold text-ink">继续上次的回答</h2><div className="mt-3 flex flex-wrap gap-2">{data.sessions.filter((s) => s.status === 'active').slice(-5).map((session) => <Button key={session.id} variant="outline" onClick={() => setView('map', { session: session.id })}>{session.kind === 'interview' ? '项目追问' : '主动回忆'} · {session.createdAt.slice(0, 10)}</Button>)}</div></section>}</>}
      {tab === 'today' && <><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold text-ink">{data.today} · 今日两份证据</h2><Button variant="outline" disabled={busy || !data.nextSkillId} onClick={() => onAction(ensureGrowthPlan(Boolean(data.plan)))}>{data.plan ? '调整未完成任务' : '生成今日任务'}</Button></div>{data.plan ? <div className="grid items-start gap-5 lg:grid-cols-2">{data.plan.tasks.map((task) => <TaskView key={`${task.id}-${data.plan!.revision}`} task={task} date={data.plan!.date} skills={data.skills} busy={busy} onSkill={onSkill} onTarget={onTarget} onOperation={onOperation} onAction={onAction} />)}</div> : <div className="rounded-xl bg-surface p-8"><p className="text-sm leading-7 text-ink-secondary">先选择目标岗位并分析 JD，再生成有依据的学习与项目任务。</p><Button className="mt-4" onClick={() => setView('targets')}>选择目标岗位</Button></div>}</>}
      {tab === 'targets' && <Targets targets={activeTargets} busy={busy} onAction={onAction} onOperation={onOperation} />}
      {tab === 'jobs' && <section className="min-w-0 rounded-xl bg-surface p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold text-ink">岗位要求与我的能力证据</h2>{selectedTarget && <Button variant="ghost" onClick={() => setView('jobs')}>查看全部目标</Button>}</div><p className="mt-2 text-sm leading-6 text-ink-secondary">{data.sampleNotice}</p>{!targets.length && <Button className="mt-5" onClick={() => setView('targets')}>加入目标 JD</Button>}{targets.map((target) => <section key={target.id} className="mt-6 border-t border-black/[0.06] pt-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold text-ink">{target.title}{target.focus && <Star className="ml-2 inline size-4 fill-amber-500 text-amber-700" />}</h3><p className="mt-1 text-sm text-ink-secondary">{target.company} · {SOURCE_NAMES[target.source]}</p><p className="mt-2 text-sm text-ink-secondary">报名资格：{target.eligibility?.label ?? '请单独核对学历、届别与工作年限。'} 技能证据不代表录用概率。</p></div><Button variant="outline" disabled={busy} onClick={() => onOperation(analyzeGrowth([target.id]))}>{target.analysisStale ? '重新分析 JD' : '更新分析'}</Button></div>{target.analysisStale && <p className="mt-3 text-sm text-amber-900">当前 JD 尚未分析或内容已变化，旧要求暂不参与学习优先级。</p>}{target.requirements.map((requirement) => <article key={requirement.id} className="mt-4 grid min-w-0 gap-3 rounded-lg bg-surface-subtle p-4 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto]"><div className="min-w-0"><h4 className="text-sm font-semibold text-ink">{requirement.skill}<span className="ml-2 text-xs font-normal text-ink-secondary">{requirement.kind === 'hard' ? '硬性条件' : requirement.kind === 'bonus' ? '加分项' : `目标 L${requirement.minimumLevel}`}</span></h4><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-ink-body">“{requirement.quote}”</p></div><div><p className="text-sm text-ink">{REQUIREMENT_STATUS[requirement.status]}{requirement.level ? ` · 当前 L${requirement.level}` : ''}</p>{requirement.skillId && <button className="mt-2 text-sm text-brand-foreground underline" onClick={() => onSkill(requirement.skillId!)}>查看能力清单与待补足项</button>}{requirement.proofIds.map((id) => <button key={id} className="mt-1 block text-xs text-brand-foreground underline" onClick={() => setView('map', { skill: requirement.skillId!, evidence: id })}>回看证据 {id.slice(0, 6)}</button>)}</div>{requirement.skillId && <Button size="sm" variant="outline" disabled={busy || target.analysisStale} onClick={() => onOperation(startGrowthSession([requirement.skillId!]))}>验证这项能力</Button>}</article>)}</section>)}</section>}
      {tab === 'history' && <History key={data.settings.dailyMinutes} minutes={data.settings.dailyMinutes} busy={busy} onAction={onAction} onSkill={onSkill} />}
    </>}
    <footer className="flex flex-wrap gap-4 text-xs text-ink-secondary"><Link className="hover:underline" to="/jobs">查看真实岗位</Link><Link className="hover:underline" to="/profile">求职画像</Link></footer>
  </div>
}
