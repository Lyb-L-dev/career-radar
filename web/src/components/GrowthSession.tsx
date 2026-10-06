import { readStored, writeStored } from '@/lib/browserState'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { getGrowthSession, requestGrowthHint, submitGrowthAnswer } from '@/services/growth'
import type { GrowthOperation, GrowthQuestion, GrowthSkill } from '@/services/growth'

function AnswerForm({ sessionId, question, busy, onOperation }: { sessionId: string; question: GrowthQuestion; busy: boolean; onOperation: (promise: Promise<GrowthOperation>) => void }) {
  const draftKey = `career-growth-answer-${sessionId}-${question.id}`
  const [answer, setAnswer] = useState(() => question.submittedAnswer ?? readStored(draftKey) ?? '')
  const submitted = question.submittedAnswer !== undefined
  return <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onOperation(submitGrowthAnswer(sessionId, question.id, answer)) }}>
    <p className="whitespace-pre-wrap break-words text-lg leading-8 text-ink">{question.text}</p>
    {question.code && <pre className="max-h-80 overflow-auto rounded-lg bg-surface-subtle p-4 text-sm"><code>{question.code}</code></pre>}
    <p className="text-xs text-ink-secondary">{question.assisted ? '本次为提示后练习，帮助建立理解。' : '先合上资料，用自己的话回答。'} 回答会保存在本机，随时可以继续。</p>
    {question.hint && <div className="rounded-lg bg-brand-soft p-4 text-sm leading-7 text-ink"><h3 className="font-semibold">讲解</h3><p className="mt-2 whitespace-pre-wrap break-words">{question.hint}</p></div>}
    <label className="block text-sm font-medium text-ink">我的回答<Textarea aria-label="我的回答" className="mt-2" rows={7} value={answer} required maxLength={30000} disabled={busy || submitted} onChange={(e) => { setAnswer(e.target.value); writeStored(draftKey, e.target.value) }} /></label>
    {submitted && <p role="status" className="text-sm text-ink-secondary">答案已保存。评分失败时，使用任务提示中的“重试”，无需重新输入。</p>}
    <div className="flex flex-wrap gap-2"><Button type="submit" disabled={busy || submitted || !answer.trim()}>提交回答</Button><Button type="button" variant="outline" disabled={busy || submitted || Boolean(question.hint)} onClick={() => onOperation(requestGrowthHint(sessionId, question.id))}>不会，先教我</Button><Button type="button" variant="ghost" disabled={busy || submitted} onClick={() => onOperation(submitGrowthAnswer(sessionId, question.id, '', true))}>暂时跳过</Button></div>
  </form>
}

export default function GrowthSession({ sessionId, skills, busy, onOperation, onClose, onEvidence }: { sessionId: string; skills: GrowthSkill[]; busy: boolean; onOperation: (promise: Promise<GrowthOperation>) => void; onClose: () => void; onEvidence: () => void }) {
  const query = useQuery({ queryKey: ['growth', 'session', sessionId], queryFn: () => getGrowthSession(sessionId), refetchInterval: busy ? 1000 : false })
  if (query.isPending) return <section className="py-8 text-sm text-ink-secondary">正在加载测评…</section>
  if (query.isError && !query.data) return <section><p className="text-sm text-danger">测评读取失败。</p><Button onClick={() => void query.refetch()}>重试</Button></section>
  const session = query.data
  const answered = session.questions.filter(question => question.answered)
  const question = session.questions[session.currentIndex]
  return <section className="mx-auto max-w-4xl rounded-xl bg-surface p-5 md:p-7" aria-label="主动回忆与面试追问">
    {query.isError && <p role="status" className="mb-3 text-sm text-danger">刷新失败，保留本次回答。<Button variant="ghost" onClick={() => void query.refetch()}>重试</Button></p>}
    <div className="mb-5 flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold text-ink">{session.kind === 'interview' ? '项目实现追问' : session.kind === 'baseline' ? '初次能力短测' : '主动回忆'}{question && ` · ${skills.find((s) => s.id === question.skillId)?.name ?? ''}`}</h2><p className="mt-1 text-sm text-ink-secondary">{session.status === 'completed' ? '本轮已完成，证据已保存。' : session.status === 'generating' ? '题目正在生成；已生成的题目会保留。' : `第 ${session.currentIndex + 1} 题 · 可暂停后继续`}</p></div><Button variant="ghost" onClick={onClose}>返回来源视图</Button></div>
    {session.status === 'active' && question && <AnswerForm key={question.id} sessionId={session.id} question={question} busy={busy} onOperation={onOperation} />}
    <div className="mt-6 space-y-4">{answered.map((q, index) => <details key={q.id} open={index === answered.length - 1} className="rounded-lg bg-surface-subtle p-4"><summary className="cursor-pointer text-sm font-medium text-ink">{q.assisted ? '提示后练习' : '本次回答'} · {q.passed ? '评分点通过' : q.points?.length ? '发现待补足项' : '已跳过'}</summary><div className="mt-3 space-y-3 reading-copy text-ink-body"><p>{q.text}</p><p className="whitespace-pre-wrap break-words">{q.submittedAnswer}</p><p className="whitespace-pre-wrap break-words">{q.feedback}</p>{q.points?.map((point) => <p key={point.pointId}>{skills.find((s) => s.id === q.skillId)?.points.find((p) => p.id === point.pointId)?.name ?? point.pointId}：{point.reason}</p>)}{q.teaching && <div><h3 className="font-semibold">针对本次回答的讲解</h3><p className="mt-1 whitespace-pre-wrap break-words">{q.teaching}</p></div>}</div></details>)}</div>
    {session.status === 'completed' && <Button className="mt-5" variant="outline" onClick={onEvidence}>查看更新后的能力证据</Button>}
  </section>
}
