import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Star,
  Copy,
  Send,
  ExternalLink,
  CheckCircle2,
  XCircle,
  CircleHelp,
  ShieldCheck,
  Sparkles,
  Gauge,
  History,
  FileUser,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { MatchBadge, JobStatusBadge, DifficultyMeter, Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState, EmptyState } from '@/components/common/StateViews'
import { ReputationCard } from '@/components/jobs/ReputationCard'
import { useJob, useToggleFavorite, useMarkApplied } from '@/hooks/useJobs'
import { useCreateApplication, useJobApplications } from '@/hooks/useApplications'
import { APPLICATION_STATUS_LABEL, JOB_TYPE_LABEL } from '@/types'
import type { JobChange } from '@/types'
import { cn } from '@/lib/utils'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-black/[0.05] pb-5 last:border-0 last:pb-0">
      <h3 className="mb-2.5 text-[15px] font-semibold text-ink">{title}</h3>
      {children}
    </section>
  )
}

function BulletList({ items }: { items: string[] }) {
  if (items.length === 0) return <p className="text-[13px] text-ink-tertiary">暂无内容</p>
  return (
    <ul className="space-y-1.5">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2 text-[14px] leading-relaxed text-ink-body">
          <span className="mt-[9px] size-1 shrink-0 rounded-full bg-ink-tertiary" />
          {it}
        </li>
      ))}
    </ul>
  )
}

function DiffDialog({ change, open, onOpenChange }: { change: JobChange | null; open: boolean; onOpenChange: (v: boolean) => void }) {
  const [mode, setMode] = useState<'all' | 'added' | 'removed'>('all')
  if (!change?.diff) return null
  const showAdded = mode !== 'removed'
  const showRemoved = mode !== 'added'
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-xl sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-ink">内容差异 · {change.summary}</DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-2 text-[13px]">
          <span className="text-ink-secondary">查看：</span>
          {(['all', 'added', 'removed'] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                'rounded-md px-2.5 py-1 transition-colors',
                mode === m ? 'bg-brand-soft text-brand-foreground font-medium' : 'text-ink-secondary hover:bg-black/[0.04]',
              )}
            >
              {m === 'all' ? '完整版本' : m === 'added' ? '只看新增' : '只看删除'}
            </button>
          ))}
        </div>
        <div className="max-h-[50vh] space-y-1.5 overflow-auto rounded-lg bg-surface-subtle p-4 font-mono text-[13px] leading-relaxed scrollbar-thin">
          {showRemoved &&
            change.diff.removed.map((line, i) => (
              <p key={`r-${i}`} className="rounded bg-danger-soft/70 px-2 py-1 text-danger">
                − {line}
              </p>
            ))}
          {showAdded &&
            change.diff.added.map((line, i) => (
              <p key={`a-${i}`} className="rounded bg-success-soft px-2 py-1 text-success">
                + {line}
              </p>
            ))}
          {mode !== 'all' && (
            <p className="pt-1 text-[12px] text-ink-tertiary font-sans">
              {mode === 'added' ? '已隐藏未变化与删除的内容。' : '已隐藏未变化与新增的内容。'}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: job, isLoading, isError, refetch } = useJob(id ?? '')
  const toggleFav = useToggleFavorite()
  const markApplied = useMarkApplied()
  const { data: applications } = useJobApplications(id ?? '')
  const createApplication = useCreateApplication()
  const [diffChange, setDiffChange] = useState<JobChange | null>(null)
  const [diffOpen, setDiffOpen] = useState(false)

  if (isLoading) return <PageSkeleton />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!job)
    return (
      <EmptyState
        title="没有找到这个岗位"
        description="岗位可能已被移除，或链接有误。"
        actions={<Button variant="outline" onClick={() => navigate('/jobs')}>返回岗位中心</Button>}
      />
    )

  const copyInfo = () => {
    navigator.clipboard.writeText(`${job.title}｜${job.companyName}｜${job.city}\n${job.sourceUrl}`)
    toast.success('岗位信息已复制')
  }
  const httpApplyUrl = job.applyUrl && /^https?:\/\//i.test(job.applyUrl) ? job.applyUrl : undefined
  const emailApplyUrl = job.applyUrl?.toLowerCase().startsWith('mailto:') ? job.applyUrl : undefined
  const officialPageUrl = /^https?:\/\//i.test(job.sourceUrl) ? job.sourceUrl : undefined
  const officialTarget = httpApplyUrl ?? officialPageUrl
  const isNotice = job.type === 'notice'
  const latestApplication = applications?.[0]

  const startApplication = () => {
    createApplication.mutate(job.id, {
      onSuccess: (result) => {
        toast.success('申请任务已创建，正在评估岗位匹配度')
        navigate(`/applications/${result.applicationId}`)
      },
      onError: (error) => {
        toast.error('无法创建申请任务', {
          description: error instanceof Error ? error.message : '请检查私有画像和本地 API。',
        })
      },
    })
  }

  return (
    <div className="space-y-5">
      <Link to="/jobs" className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors">
        <ArrowLeft className="size-4" />
        返回岗位中心
      </Link>

      {/* 岗位信息区 */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[24px] font-semibold text-ink">{job.title}</h1>
              <JobStatusBadge status={job.status} />
              {job.highlyRecommended && <Pill tone="orange">高度推荐</Pill>}
            </div>
            <p className="mt-1.5 text-[15px] text-ink-secondary">
              {job.companyName} · {job.city} · {JOB_TYPE_LABEL[job.type]}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-ink-secondary">
              <span>发布时间 {job.publishedAt ?? '未知'}</span>
              <span>首次发现 {job.firstSeenAt}</span>
              <span>最后更新 {job.lastUpdatedAt}</span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className="text-[13px] text-ink-secondary">届别 <MatchBadge level={job.gradYearMatch} /></span>
              <span className="text-[13px] text-ink-secondary">能力 <MatchBadge level={job.abilityMatch} /></span>
              <span className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary">难度 <DifficultyMeter value={job.difficulty} /></span>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-stretch gap-2 sm:flex-row sm:items-center">
            {latestApplication ? (
              <Button asChild variant="outline" className="border-brand/30 text-brand-foreground">
                <Link to={`/applications/${latestApplication.id}`}>
                  <FileUser className="size-4" />
                  查看申请材料
                </Link>
              </Button>
            ) : (
              <Button
                variant="outline"
                className="border-brand/30 text-brand-foreground"
                disabled={isNotice || job.jdComplete === false || createApplication.isPending}
                onClick={startApplication}
                title={
                  isNotice
                    ? '招聘通知不是具体岗位'
                    : job.jdComplete === false
                      ? '需要先获取完整 JD'
                      : '先评估匹配度，人工批准后才生成材料'
                }
              >
                {createApplication.isPending ? <Loader2 className="size-4 animate-spin" /> : <FileUser className="size-4" />}
                {isNotice ? '通知暂不生成材料' : job.jdComplete === false ? 'JD 不完整，暂不生成' : 'AI 定制申请材料'}
              </Button>
            )}
            {officialTarget ? (
              <Button asChild className="bg-brand hover:bg-brand-hover text-white">
                <a href={officialTarget} target="_blank" rel="noopener noreferrer">
                  {isNotice ? '打开官方招聘通知' : httpApplyUrl ? '前往官网投递' : '打开官网岗位页'}
                  <ExternalLink className="size-4" />
                </a>
              </Button>
            ) : (
              <div className="rounded-lg bg-warning-soft px-3 py-2 text-[12px] text-warning">
                当前页面未识别到可信投递链接，请查看 JD 中的联系方式。
              </div>
            )}
            {emailApplyUrl && (
              <Button asChild variant="outline">
                <a href={emailApplyUrl}>
                  <Send className="size-4" />
                  邮件投递
                </a>
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => {
                toggleFav.mutate(job.id)
                toast.success(job.isFavorite ? '已取消收藏' : '岗位已收藏')
              }}
            >
              <Star className={cn('size-4', job.isFavorite && 'fill-highlight text-highlight')} />
              {job.isFavorite ? '已收藏' : '收藏岗位'}
            </Button>
            <Button variant="outline" onClick={copyInfo}>
              <Copy className="size-4" />
              复制信息
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                markApplied.mutate({ id: job.id, applied: !job.isApplied })
                toast.success(job.isApplied ? '已取消投递标记' : '已标记为已投递')
              }}
            >
              <Send className="size-4" />
              {job.isApplied ? '取消已投递' : '标记已投递'}
            </Button>
          </div>
        </div>
        {!httpApplyUrl && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-surface-subtle px-4 py-3">
            <span className="text-[13px] text-ink-secondary">
              {emailApplyUrl ? '该岗位通过邮箱接收简历，可打开官网岗位页核对要求后投递。' : '官网未提供独立申请按钮，请在岗位来源页确认最新投递方式。'}
            </span>
            {job.contactEmail && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(job.contactEmail!)
                  toast.success('JD 中的邮箱已复制')
                }}
              >
                复制 JD 中的邮箱
              </Button>
            )}
          </div>
        )}
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        {/* 左侧主体 */}
        <div className="space-y-5">
          <Card className="space-y-5">
            <Section title={isNotice ? '通知概览' : '岗位概览'}>
              <p className="text-[14px] leading-relaxed text-ink-body">{job.overview}</p>
            </Section>
            <Section title={isNotice ? '招聘通知正文' : '工作职责'}>
              <BulletList items={job.responsibilities} />
            </Section>
            <Section title={isNotice ? '资格条件' : '任职要求'}>
              <BulletList items={job.requirements} />
            </Section>
            <Section title="加分项">
              <BulletList items={job.plusPoints} />
            </Section>
            <Section title="工作地点">
              <p className="text-[14px] text-ink-body">{job.locationDetail}</p>
            </Section>
            <Section title="投递方式">
              <p className="text-[14px] text-ink-body">{job.applyMethod}</p>
            </Section>
            <Section title={isNotice ? '完整通知原文' : '完整 JD 原文'}>
              {job.jdComplete === false && (
                <div className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-[12px] text-warning">
                  JD 不完整：{job.jdIncompleteReason || '官网当前页面只提供了岗位摘要，请打开来源页人工确认。'}
                </div>
              )}
              <div className="rounded-lg bg-surface-subtle p-4 text-[13px] leading-relaxed text-ink-body whitespace-pre-wrap">
                {job.jdText}
              </div>
            </Section>
          </Card>

          <ReputationCard jobId={job.id} />

          {/* 更新历史 */}
          <Card>
            <CardTitle>更新历史</CardTitle>
            {job.history.length === 0 ? (
              <p className="text-[13px] text-ink-tertiary">暂无变化记录</p>
            ) : (
              <ol className="relative space-y-4 border-l border-black/[0.08] pl-5">
                {job.history.map((h) => (
                  <li key={h.id} className="relative">
                    <span className="absolute -left-[26px] top-1 size-2.5 rounded-full border-2 border-surface bg-brand" />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[14px] font-medium text-ink">{h.summary}</p>
                        <p className="text-[12px] text-ink-tertiary">{h.time}</p>
                      </div>
                      {h.diff && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setDiffChange(h)
                            setDiffOpen(true)
                          }}
                        >
                          <History className="size-3.5" />
                          查看差异
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        {/* 右侧固定侧栏 */}
        <div className="space-y-5 xl:sticky xl:top-24 self-start">
          {latestApplication && (
            <Card>
              <div className="flex items-center gap-2">
                <FileUser className="size-4 text-brand" />
                <h3 className="text-[15px] font-semibold text-ink">AI 申请材料</h3>
                {latestApplication.isRunning && <Loader2 className="ml-auto size-4 animate-spin text-brand" />}
              </div>
              <p className="mt-3 text-[13px] font-medium text-ink">
                {APPLICATION_STATUS_LABEL[latestApplication.status]}
              </p>
              <Progress value={latestApplication.progress} className="mt-2 h-1.5" />
              <p className="mt-2 text-[12px] leading-relaxed text-ink-secondary">{latestApplication.nextAction}</p>
              <Button asChild variant="outline" size="sm" className="mt-3 w-full">
                <Link to={`/applications/${latestApplication.id}`}>查看评估、审批与文件</Link>
              </Button>
            </Card>
          )}
          <Card>
            <div className="mb-3 flex items-center gap-2">
              <Sparkles className="size-4 text-brand" />
              <h3 className="text-[15px] font-semibold text-ink">AI 匹配分析</h3>
            </div>
            <p className="rounded-lg bg-brand-soft px-3.5 py-3 text-[13px] leading-relaxed text-brand-foreground">
              {job.analysis.advice}
            </p>
            <p className="mt-3 text-[13px] text-ink-secondary">{job.analysis.conclusion}</p>
            <div className="mt-4 space-y-3 text-[13px]">
              <div>
                <p className="mb-1.5 font-medium text-ink">已具备能力</p>
                <div className="flex flex-wrap gap-1.5">
                  {job.analysis.hasSkills.length ? (
                    job.analysis.hasSkills.map((s) => <Pill key={s} tone="green">{s}</Pill>)
                  ) : (
                    <span className="text-ink-tertiary">暂无明显匹配项</span>
                  )}
                </div>
              </div>
              <div>
                <p className="mb-1.5 font-medium text-ink">缺失能力</p>
                <div className="flex flex-wrap gap-1.5">
                  {job.analysis.missingSkills.length ? (
                    job.analysis.missingSkills.map((s) => <Pill key={s} tone="amber">{s}</Pill>)
                  ) : (
                    <span className="text-ink-tertiary">无</span>
                  )}
                </div>
              </div>
              <div>
                <p className="mb-1.5 font-medium text-ink">建议优先补充</p>
                <ul className="space-y-1">
                  {job.analysis.suggestions.map((s, i) => (
                    <li key={i} className="flex gap-2 text-ink-body">
                      <span className="mt-[9px] size-1 shrink-0 rounded-full bg-brand" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Card>

          <Card>
            <div className="mb-3 flex items-center gap-2">
              <Gauge className="size-4 text-warning" />
              <h3 className="text-[15px] font-semibold text-ink">岗位难度 {job.difficulty}/10</h3>
            </div>
            <ul className="space-y-2.5">
              {job.difficultyFactors.map((f) => (
                <li key={f.label} className="flex items-start justify-between gap-3 text-[13px]">
                  <div>
                    <p className="font-medium text-ink">{f.label}</p>
                    <p className="text-ink-tertiary">{f.note}</p>
                  </div>
                  <Pill tone={f.level === '高' ? 'red' : f.level === '中' ? 'amber' : 'green'}>{f.level}</Pill>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="size-4 text-success" />
              <h3 className="text-[15px] font-semibold text-ink">来源可信度</h3>
            </div>
            <dl className="space-y-2.5 text-[13px]">
              {[
                ['来源', job.source.site],
                ['来源页面', job.source.page],
                ['抓取方式', job.source.method],
                ['最后验证', job.source.lastVerifiedAt],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="shrink-0 text-ink-tertiary">{k}</dt>
                  <dd className="truncate text-right text-ink-body" title={v}>{v}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-3">
                <dt className="text-ink-tertiary">URL 校验</dt>
                <dd className="flex items-center gap-1 text-success">
                  {job.source.urlVerified ? (
                    <>
                      <CheckCircle2 className="size-3.5" />
                      通过页面候选校验
                    </>
                  ) : (
                    <>
                      <XCircle className="size-3.5 text-danger" />
                      未通过
                    </>
                  )}
                </dd>
              </div>
            </dl>
            <p className="mt-3 flex items-start gap-1.5 text-[12px] text-ink-tertiary">
              <CircleHelp className="mt-0.5 size-3.5 shrink-0" />
              岗位信息均来自企业官网公开页面，系统会对详情页 URL 做真实性校验。
            </p>
          </Card>
        </div>
      </div>

      <DiffDialog change={diffChange} open={diffOpen} onOpenChange={setDiffOpen} />
    </div>
  )
}
