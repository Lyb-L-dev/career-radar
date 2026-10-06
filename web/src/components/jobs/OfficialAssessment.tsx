import { Link } from 'react-router'
import { Loader2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { Pill } from '@/components/common/Badges'
import { Button } from '@/components/ui/button'
import { useOfficialScreeningStatus, useStartOfficialScreening } from '@/hooks/useJobs'
import type { Job, OfficialQualification } from '@/types'

export function EligibilityBadge({ result }: { result?: OfficialQualification }) {
  const verdict = result?.verdict ?? 'review'
  return <span title={result?.summary}><Pill tone={verdict === 'eligible' ? 'green' : verdict === 'ineligible' ? 'red' : 'amber'} className={verdict === 'eligible' ? 'text-[#157347]' : verdict === 'ineligible' ? 'text-[#B42318]' : 'text-[#965000]'}>{verdict === 'eligible' ? '资格符合' : verdict === 'ineligible' ? '明确不符' : '需核对资格'}</Pill></span>
}

const DIRECTIONS = { ai_application: 'AI 应用开发', agent_rag: 'Agent / RAG', fde_delivery: 'FDE / 技术交付', backend: '后端开发', other: '其它方向' }

export function OfficialAssessmentPanel({ job }: { job: Job }) {
  const start = useStartOfficialScreening()
  const { data: task } = useOfficialScreeningStatus()
  const fit = job.aiAssessment?.result
  const running = task?.status === 'running'
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>资格与投递优先级</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <EligibilityBadge result={job.eligibility} />
            {job.priority && <span className="text-sm font-medium text-ink">{job.priority.label}{job.priority.score !== null && job.priority.tier !== 'defer' ? ` · ${job.priority.score}/100` : ''}</span>}
          </div>
        </div>
        <Button variant="outline" disabled={running || start.isPending || job.eligibility?.verdict === 'ineligible' || job.type === 'notice' || job.jdComplete === false} onClick={() => start.mutate({ ids: [job.id], force: job.aiAssessment?.status === 'current' }, {
          onSuccess: () => toast.success('已开始评估，结果会自动更新'),
          onError: (error) => toast.error(error.message),
        })}>
          {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {job.jdComplete === false ? '先核对完整 JD' : job.aiAssessment?.status === 'current' ? '重新评估' : 'AI 评估方向'}
        </Button>
      </div>
      <p className="mt-3 text-sm text-ink-secondary">{job.eligibility?.summary ?? '尚未核验资格'} · 核对日期 {job.eligibility?.checked_at ?? '未知'}</p>
      <Link to="/profile" className="mt-2 inline-block text-sm text-brand underline">补充学籍、毕业月份与正式工作年限</Link>
      <div className="mt-4 grid gap-x-6 gap-y-4 md:grid-cols-2">
        {job.eligibility?.checks.map((check) => (
          <div key={check.dimension}>
            <p className="text-sm font-medium text-ink">{check.requirement} <span className={check.verdict === 'unmet' ? 'text-[#B42318]' : check.verdict === 'met' ? 'text-[#157347]' : 'text-[#965000]'}>{check.verdict === 'met' ? '符合' : check.verdict === 'unmet' ? '不符' : '未确认'}</span></p>
            <p className="mt-1 text-xs text-ink-secondary">{check.candidate_fact || '画像中尚无对应事实'}</p>
            <blockquote className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-body">{check.job_quote ? `JD 证据：“${check.job_quote}”` : '官网未明确该条件。'}{!check.required && '（未作硬性排除）'}</blockquote>
          </div>
        ))}
      </div>
      <details className="mt-5 border-t border-black/[0.08] pt-4"><summary className="cursor-pointer text-sm font-medium text-brand-foreground">画像匹配判断与引用依据 · 展开分析</summary>
        {fit ? (
          <>
            <p className="text-sm font-medium text-ink">{DIRECTIONS[fit.direction]} · 方向相关 {fit.direction_score}/100 · 项目与技能证据 {fit.evidence_score}/100</p>
            <p className="mt-2 reading-copy text-ink-body">{fit.summary}</p>
            <p className="mt-1 text-xs text-ink-secondary">{job.aiAssessment?.model} · {job.aiAssessment?.evaluatedAt} · 排序分数用于确定阅读顺序，不代表录取概率。</p>
            {fit.matches.length > 0 && <h3 className="mt-4 text-sm font-semibold text-ink">已有证据</h3>}
            {fit.matches.map((item, index) => (
              <div key={index} className="mt-3 space-y-1 text-sm leading-relaxed">
                <p className="font-medium text-ink">{item.requirement}：{item.reason}</p>
                <p className="text-ink-secondary">岗位原文：“{item.job_quote}”</p>
                <p className="text-ink-body">画像原文：“{item.candidate_quote}”</p>
              </div>
            ))}
            {fit.gaps.length > 0 && <h3 className="mt-4 text-sm font-semibold text-ink">差距与待确认项</h3>}
            {fit.gaps.map((item, index) => <p key={index} className="mt-2 reading-copy text-ink-body">{item.detail}<span className="block text-xs text-ink-secondary">岗位原文：“{item.job_quote}”</span></p>)}
            {fit.next_steps.length > 0 && <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-ink-body">{fit.next_steps.map((item, i) => <li key={i}>{item}</li>)}</ul>}
            {fit.grounding_warnings.map((item, i) => <p key={i} className="mt-2 text-xs text-[#965000]">{item}</p>)}
          </>
        ) : (
          <p className="text-sm text-ink-secondary">{job.eligibility?.verdict === 'ineligible' ? '当前硬性资格不符，暂缓投递；资格与技能匹配分别判断。' : job.aiAssessment?.status === 'stale' ? '画像、岗位正文或模型配置已变化，请重新评估后查看排序。' : job.aiAssessment?.status === 'failed' ? `评估未完成：${job.aiAssessment.error}` : '方向与项目匹配尚未评估。点击 AI 评估后可查看有原文证据的分析。'}</p>
        )}
      </details>
    </Card>
  )
}
