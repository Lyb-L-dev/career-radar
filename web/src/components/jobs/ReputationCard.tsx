import { useMemo, useState } from 'react'
import {
  CheckCircle2,
  Clock3,
  ExternalLink,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldAlert,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { Pill } from '@/components/common/Badges'
import { Button } from '@/components/ui/button'
import { useJobReputation, useReputationHealth, useStartReputationScan } from '@/hooks/useReputation'
import type { ReputationAnalysis, ReputationScanStatus } from '@/types'

const TERMINAL = new Set<ReputationScanStatus>(['completed', 'partial', 'failed', 'interrupted'])
const RISK_LABEL: Record<ReputationAnalysis['risk_level'], string> = {
  low: '暂未发现集中风险',
  medium: '存在需核实信号',
  high: '存在较强风险信号',
  unknown: '证据不足',
}
const CONFIDENCE_LABEL: Record<ReputationAnalysis['confidence'], string> = {
  low: '低置信度',
  medium: '中置信度',
  high: '高置信度',
}

function riskTone(level: ReputationAnalysis['risk_level']): 'green' | 'amber' | 'red' | 'gray' {
  if (level === 'low') return 'green'
  if (level === 'medium') return 'amber'
  if (level === 'high') return 'red'
  return 'gray'
}

export function ReputationCard({ jobId }: { jobId: string }) {
  const health = useReputationHealth()
  const report = useJobReputation(jobId)
  const start = useStartReputationScan(jobId)
  const [showAll, setShowAll] = useState(false)
  const scan = report.data
  const active = scan?.status === 'pending' || scan?.status === 'running'
  const jobEvidenceCount = (scan?.evidence ?? []).filter((item) => item.relevanceScope === 'job').length
  const companyEvidenceCount = (scan?.evidence ?? []).length - jobEvidenceCount
  const evidenceById = useMemo(
    () => new Map((scan?.evidence ?? []).map((item) => [item.id, item])),
    [scan?.evidence],
  )

  const startScan = () => {
    start.mutate(undefined, {
      onSuccess: () => toast.success('口碑调查已开始', { description: '正在依次读取四个平台，请保持 Chrome 开启。' }),
      onError: (error) => toast.error('无法开始口碑调查', { description: error.message }),
    })
  }

  const displayedEvidence = showAll ? (scan?.evidence ?? []) : (scan?.evidence ?? []).slice(0, 8)

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <MessageSquare className="size-4 text-brand" />
            <CardTitle>岗位口碑调查</CardTitle>
          </div>
          <p className="mt-1 text-[12px] text-ink-tertiary">
            只保留正文明确命中公司名称的公开内容，并区分“具体岗位相关”和“公司相关”
          </p>
        </div>
        <Button
          size="sm"
          onClick={startScan}
          disabled={start.isPending || active || health.isLoading || health.data?.available === false}
          className="bg-brand text-white hover:bg-brand-hover"
        >
          {start.isPending || active ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
          {active ? '调查进行中' : scan ? '重新调查' : '开始调查'}
        </Button>
      </div>

      {health.data?.available === false && (
        <div className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2.5 text-[12px] text-warning">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          <span>OpenCLI 当前不可用：{health.data.message || '请检查 Chrome 扩展与平台登录状态。'}</span>
        </div>
      )}

      {!scan && !report.isLoading && (
        <div className="rounded-lg bg-surface-subtle px-4 py-5 text-center">
          <p className="text-[13px] font-medium text-ink">尚未调查这个岗位的公开口碑</p>
          <p className="mt-1 text-[12px] leading-5 text-ink-tertiary">
            由你手动触发，系统不会批量扫描全部岗位，也不会执行发帖、评论、点赞或私信。
          </p>
        </div>
      )}

      {report.isLoading && (
        <div className="flex items-center justify-center gap-2 py-8 text-[13px] text-ink-tertiary">
          <Loader2 className="size-4 animate-spin" />读取历史调查…
        </div>
      )}

      {scan && (
        <>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {scan.platforms.map((platform) => (
              <div key={platform.key} className="rounded-lg bg-surface-subtle px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-ink">{platform.label}</span>
                  {platform.status === 'running' || platform.status === 'waiting' ? (
                    <Clock3 className="size-3.5 text-warning" />
                  ) : platform.status === 'success' ? (
                    <CheckCircle2 className="size-3.5 text-success" />
                  ) : (
                    <XCircle className="size-3.5 text-danger" />
                  )}
                </div>
                <p className="mt-1 text-[11px] text-ink-tertiary">
                  {platform.status === 'success' ? `${platform.evidenceCount} 条证据` : platform.error || '等待执行'}
                </p>
              </div>
            ))}
          </div>

          {active && (
            <div className="flex items-center gap-2 rounded-lg bg-brand-soft px-3 py-2.5 text-[12px] text-brand-foreground">
              <Loader2 className="size-4 animate-spin" />
              浏览器正在按平台串行搜索；可以浏览其他页面，但请暂时不要关闭 Chrome。
            </div>
          )}

          {TERMINAL.has(scan.status) && scan.evidence.length > 0 && jobEvidenceCount === 0 && (
            <div className="rounded-lg bg-warning-soft px-3 py-2.5 text-[12px] leading-5 text-warning">
              本次没有找到同时明确提及“该公司 + 该岗位”的公开内容。下面仅有公司级口碑，不能直接代表这个岗位。
            </div>
          )}

          {scan.analysis && (
            <div className="space-y-4 rounded-xl border border-black/[0.06] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Pill tone={riskTone(scan.analysis.risk_level)}>{RISK_LABEL[scan.analysis.risk_level]}</Pill>
                <Pill tone="gray">{CONFIDENCE_LABEL[scan.analysis.confidence]}</Pill>
                <span className="text-[11px] text-ink-tertiary">
                  岗位级 {jobEvidenceCount} 条 · 公司级 {companyEvidenceCount} 条
                </span>
              </div>
              <p className="text-[14px] leading-6 text-ink-body">{scan.analysis.overall_summary}</p>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="mb-2 text-[13px] font-medium text-success">正向信号</p>
                  {scan.analysis.positive_signals.length ? (
                    <ul className="space-y-1.5 text-[13px] text-ink-body">
                      {scan.analysis.positive_signals.map((item) => <li key={item}>· {item}</li>)}
                    </ul>
                  ) : <p className="text-[12px] text-ink-tertiary">没有足够证据形成结论</p>}
                </div>
                <div>
                  <p className="mb-2 text-[13px] font-medium text-danger">风险与待核实项</p>
                  {scan.analysis.risk_signals.length ? (
                    <ul className="space-y-1.5 text-[13px] text-ink-body">
                      {scan.analysis.risk_signals.map((item) => <li key={item}>· {item}</li>)}
                    </ul>
                  ) : <p className="text-[12px] text-ink-tertiary">没有足够证据形成结论</p>}
                </div>
              </div>

              {scan.analysis.topics.length > 0 && (
                <div className="space-y-2 border-t border-black/[0.05] pt-3">
                  {scan.analysis.topics.map((topic) => (
                    <div key={`${topic.name}-${topic.summary}`} className="text-[13px] leading-5">
                      <span className="font-medium text-ink">{topic.name}：</span>
                      <span className="text-ink-body">{topic.summary}</span>
                      {topic.evidence_ids.map((id) => {
                        const evidence = evidenceById.get(id)
                        if (!evidence?.url) return null
                        return (
                          <a
                            key={id}
                            href={evidence.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-1 text-brand hover:underline"
                            title={`${evidence.platformLabel}：${evidence.title}`}
                          >
                            [{scan.evidence.findIndex((item) => item.id === id) + 1}]
                          </a>
                        )
                      })}
                    </div>
                  ))}
                </div>
              )}

              {scan.analysis.interview_tips.length > 0 && (
                <div className="rounded-lg bg-brand-soft px-3 py-2.5">
                  <p className="text-[12px] font-medium text-brand-foreground">面试时建议确认</p>
                  <ul className="mt-1 space-y-1 text-[12px] text-brand-foreground/90">
                    {scan.analysis.interview_tips.map((item) => <li key={item}>· {item}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}

          {scan.errors.length > 0 && TERMINAL.has(scan.status) && (
            <div className="rounded-lg bg-warning-soft px-3 py-2.5 text-[12px] text-warning">
              {scan.errors.join('；')}
            </div>
          )}

          {displayedEvidence.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[13px] font-medium text-ink">原始公开线索</p>
                {scan.evidence.length > 8 && (
                  <Button variant="ghost" size="sm" onClick={() => setShowAll((value) => !value)}>
                    {showAll ? '收起' : `查看全部 ${scan.evidence.length} 条`}
                  </Button>
                )}
              </div>
              {displayedEvidence.map((item, index) => (
                <div key={item.id} className="rounded-lg border border-black/[0.05] px-3 py-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-ink">[{index + 1}] {item.title}</p>
                      <p className="mt-1 line-clamp-3 text-[12px] leading-5 text-ink-secondary">{item.excerpt}</p>
                      <p className="mt-1 text-[11px] text-ink-tertiary">
                        {item.platformLabel}
                        {item.relevanceScope === 'job' ? ' · 公司+岗位相关' : ' · 公司相关'}
                        {item.publishedAt ? ` · ${item.publishedAt}` : ''}
                        {item.interactionCount ? ` · 互动 ${item.interactionCount}` : ''}
                      </p>
                    </div>
                    {item.url && (
                      <a href={item.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-brand">
                        <ExternalLink className="size-4" />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="flex items-start gap-1.5 text-[11px] leading-5 text-ink-tertiary">
            <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
            {scan.disclaimer} 调查时间：{scan.finishedAt ?? scan.updatedAt}。
          </p>
        </>
      )}
    </Card>
  )
}
