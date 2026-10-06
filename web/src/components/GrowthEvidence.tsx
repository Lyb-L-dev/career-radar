import { useLocation } from 'react-router'
import { useLocalDraft } from '@/hooks/useBrowserState'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, CircleHelp, CircleMinus, ArrowUpRight, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { getGrowthSkill, markGrowthPoint, startGrowthSession, submitGrowthProject } from '@/services/growth'
import type { GrowthOperation } from '@/services/growth'
import { POINT_STATUS, SKILL_STATUS } from '@/lib/growthMap'

export default function GrowthEvidence({ skillId, highlighted, levels, busy, onClose, onOperation, onAction, onTarget }: {
  skillId: string; highlighted: string | null; levels: string[]; busy: boolean; onClose: () => void
  onOperation: (promise: Promise<GrowthOperation>) => void; onAction: (promise: Promise<unknown>) => void
  onTarget: (id: string) => void
}) {
  const query = useQuery({ queryKey: ['growth', 'skill', skillId], queryFn: () => getGrowthSkill(skillId) })
  const [projectOpen, setProjectOpen] = useState(false)
  const draft = useLocalDraft(`career-growth-project:${skillId}`, { code: '', explanation: '', runRecord: '' })
  const { code, explanation, runRecord } = draft.value
  const setCode = (value: string) => draft.update({ code: value })
  const setExplanation = (value: string) => draft.update({ explanation: value })
  const setRunRecord = (value: string) => draft.update({ runRecord: value })
  const [showAll, setShowAll] = useState(false)
  const location = useLocation()
  const selectedEvidence = highlighted ?? (location.hash.startsWith('#evidence-') ? location.hash.slice(10) : null)
  useEffect(() => {
    if (!selectedEvidence || !query.data) return
    const frame = requestAnimationFrame(() => { const node = document.getElementById(`evidence-${selectedEvidence}`) as HTMLDetailsElement | null; if (node) { node.open = true; node.scrollIntoView({ block: 'start' }); node.focus({ preventScroll: true }) } })
    return () => cancelAnimationFrame(frame)
  }, [selectedEvidence, query.data])
  if (query.isPending) return <aside className="p-5 text-sm text-ink-secondary">正在读取技能证据…</aside>
  if (query.isError && !query.data) return <aside className="p-5"><p className="text-sm text-danger">技能证据读取失败。</p><Button variant="outline" onClick={() => void query.refetch()}>重试</Button></aside>
  const skill = query.data
  return <aside className="min-w-0 space-y-5 rounded-xl bg-white p-5" aria-label={`${skill.name}的能力证据`}>
    {query.isError && <p role="status" className="text-sm text-danger">刷新失败，保留已有证据。<Button variant="ghost" onClick={() => void query.refetch()}>重试</Button></p>}
    <div className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold text-ink">{skill.name}</h2><p className="mt-1 text-sm text-ink-secondary">{skill.level ? `Level ${skill.level} / 5 · ${SKILL_STATUS[skill.status]}` : SKILL_STATUS[skill.status]}</p></div><Button size="icon" variant="ghost" onClick={onClose} aria-label="关闭技能详情"><X className="size-4" /></Button></div>
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm"><div><dt className="text-ink-secondary">最近独立回忆</dt><dd className="mt-1 font-medium text-ink">{skill.lastRecall ?? '尚无记录'}</dd></div><div><dt className="text-ink-secondary">连续跨日通过</dt><dd className="mt-1 font-medium text-ink">{skill.streak} 次</dd></div><div className="col-span-2"><dt className="text-ink-secondary">下次复习</dt><dd className="mt-1 font-medium text-ink">{skill.nextReview ?? '测评后安排'}{skill.reviewDue && ' · 已到复习日期'}</dd></div></dl>
    <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => onOperation(startGrowthSession([skill.id]))}>开始回忆</Button><Button variant="outline" disabled={busy} onClick={() => setProjectOpen((open) => !open)}>提交项目证据</Button></div>
    {projectOpen && <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onOperation(submitGrowthProject({ skillId: skill.id, code, explanation, runRecord })) }}><h3 className="font-semibold text-ink">用项目证明我会</h3><label className="block text-sm text-ink">代码或项目材料<Textarea aria-label="代码或项目材料" className="mt-1 font-mono text-sm" value={code} onChange={(e) => setCode(e.target.value)} required maxLength={30000} rows={6} /></label><label className="block text-sm text-ink">我做了什么，为什么这样设计<Textarea aria-label="我做了什么，为什么这样设计" className="mt-1" value={explanation} onChange={(e) => setExplanation(e.target.value)} required maxLength={10000} rows={3} /></label><label className="block text-sm text-ink">真实运行或测试记录（选填）<Textarea aria-label="真实运行或测试记录（选填）" className="mt-1 font-mono text-sm" value={runRecord} onChange={(e) => setRunRecord(e.target.value)} maxLength={10000} rows={3} /></label><p className="text-xs leading-5 text-ink-secondary">材料由模型审阅，提交后会提出实现细节追问。运行记录按你的提交保存。</p><Button type="submit" disabled={busy || !code.trim() || !explanation.trim()}>审阅并开始追问</Button></form>}
    {skill.level > 0 && <p className="text-sm leading-6 text-ink-body">当前达标：{levels[skill.level - 1]}。历史最高 L{skill.highestLevel}。</p>}
    <details className="text-sm text-ink-secondary"><summary className="cursor-pointer">查看五级证据标准</summary><ol className="mt-2 space-y-2">{levels.map((level, index) => <li key={level}>L{index + 1}：{level}</li>)}</ol><p className="mt-2 text-xs">评分标准：{skill.rubricVersion}</p></details>
    <ul className="divide-y divide-black/[0.06]">{skill.points.map((point) => <li key={point.id} className="py-3"><div className="flex items-start gap-2">{point.status === 'independent' ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : point.status === 'needs_hint' ? <CircleMinus className="mt-0.5 size-4 shrink-0 text-amber-800" /> : <CircleHelp className="mt-0.5 size-4 shrink-0 text-ink-secondary" />}<span className="flex-1 text-sm text-ink">{point.name}</span><span className="text-xs text-ink-secondary">{POINT_STATUS[point.status]}</span></div>{point.evidenceId && <a className="ml-6 mt-1 inline-block text-xs text-brand-foreground underline" href={`#evidence-${point.evidenceId}`}>查看评分证据</a>}{['unassessed', 'not_learned'].includes(point.status) && <label className="ml-6 mt-1 flex items-center gap-2 text-xs text-ink-secondary"><input type="checkbox" disabled={busy} checked={point.status === 'not_learned'} onChange={(e) => onAction(markGrowthPoint(skill.id, point.id, e.target.checked))} />我尚未学习这一项</label>}</li>)}</ul>

    {skill.selfReported.length > 0 && <p className="text-xs leading-5 text-ink-secondary">画像中自述：{skill.selfReported.join('、')}。独立测评证据见下方记录。</p>}
    {skill.relevant && <div><h3 className="text-sm font-semibold text-ink">为什么现在学</h3><p className="mt-1 text-sm leading-6 text-ink-secondary">{skill.reason}</p>{skill.references.map((ref) => <button key={`${ref.targetId}-${ref.requirementId}`} className="mt-2 block w-full text-left text-sm text-brand-foreground hover:underline" onClick={() => onTarget(ref.targetId)}>{ref.title}<ArrowUpRight className="ml-1 inline size-3.5" /><span className="mt-1 block text-xs leading-5 text-ink-secondary">“{ref.quote}”</span></button>)}</div>}


    <section aria-label="能力证据记录"><h3 className="text-base font-semibold text-ink">证明我会</h3>{!skill.evidence.length ? <p className="mt-2 text-sm text-ink-secondary">第一份证据从一次独立回答开始。</p> : <div className="mt-3 divide-y divide-black/[0.06]">{(showAll || selectedEvidence ? skill.evidence : skill.evidence.slice(0, 3)).map((evidence) => <details key={evidence.id} id={`evidence-${evidence.id}`} tabIndex={-1} open={selectedEvidence === evidence.id ? true : undefined} className="scroll-mt-24 py-3"><summary className="cursor-pointer text-sm text-ink"><span className="text-xs text-ink-secondary">{evidence.createdAt.slice(0, 10)}</span><span className="ml-2">{evidence.type === 'project' ? '项目材料审阅' : evidence.type === 'interview' ? '实现细节追问' : evidence.skipped ? '已跳过' : evidence.assisted ? '提示后练习' : '独立回忆'}</span><span className="ml-2 text-xs text-ink-secondary">{evidence.skipped ? '未计分' : `${evidence.points.filter((p) => p.passed).length}/${evidence.points.length} 评分点通过`}</span></summary><div className="mt-3 space-y-3 reading-copy text-ink-body">{evidence.question && <p>{evidence.question}</p>}{evidence.questionCode && <pre className="max-h-64 overflow-auto rounded-lg bg-surface-subtle p-3 text-xs"><code>{evidence.questionCode}</code></pre>}{evidence.answer && <p className="whitespace-pre-wrap break-words rounded-lg bg-surface-subtle p-3">{evidence.answer}</p>}{evidence.code && <pre className="max-h-64 overflow-auto rounded-lg bg-surface-subtle p-3 text-xs"><code>{evidence.code}</code></pre>}{evidence.explanation && <p className="whitespace-pre-wrap break-words">{evidence.explanation}</p>}{evidence.runRecord && <div><p className="text-xs text-ink-secondary">用户提交的运行记录</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs">{evidence.runRecord}</pre></div>}{evidence.verification && <p className="text-xs text-ink-secondary">{evidence.verification}</p>}<p className="whitespace-pre-wrap break-words">{evidence.feedback}</p>{evidence.points.map((point) => <div key={point.pointId}><p className="font-medium">{skill.points.find((p) => p.id === point.pointId)?.name ?? point.pointId} · {point.passed ? '通过' : '待补足'}</p><p>{point.reason}</p>{point.answerQuote && <blockquote className="mt-1 rounded bg-surface-subtle px-3 py-2 text-xs">“{point.answerQuote}”</blockquote>}</div>)}{evidence.teaching && <p className="whitespace-pre-wrap break-words">{evidence.teaching}</p>}<p className="text-xs text-ink-secondary">评分标准：{evidence.rubricVersion}</p></div></details>)}</div>}{skill.evidence.length > 3 && <Button className="mt-3" variant="ghost" onClick={() => setShowAll(value => !value)}>{showAll ? '收起历史记录' : `查看全部 ${skill.evidence.length} 条证据`}</Button>}</section>
  </aside>
}
