import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  ArrowUpRight,
  ArrowDownRight,
  Star,
  Play,
  History,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Clock,
  MinusCircle,
  AlertTriangle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { MatchBadge, DifficultyMeter, Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState } from '@/components/common/StateViews'
import { useDashboardStats, useRuns } from '@/hooks/useData'
import { useCompanies } from '@/hooks/useCompanies'
import { useJobs, useToggleFavorite } from '@/hooks/useJobs'
import { createRun } from '@/services/runs'
import type { Job } from '@/types'
import { cn } from '@/lib/utils'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
}

function StatCard({
  label,
  value,
  delta,
  desc,
  to,
}: {
  label: string
  value: number
  delta?: number
  desc: string
  to: string
}) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(to)}
      className="group rounded-xl bg-surface p-5 text-left shadow-card transition-shadow hover:shadow-pop"
    >
      <p className="text-[13px] text-ink-secondary">{label}</p>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="text-[32px] font-semibold leading-none text-ink tabular-nums">{value}</span>
        {delta !== undefined && delta !== 0 && (
          <span
            className={cn(
              'inline-flex items-center text-[12px] font-medium',
              delta > 0 ? 'text-success' : 'text-ink-tertiary',
            )}
          >
            {delta > 0 ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}
            {Math.abs(delta)} 较昨日
          </span>
        )}
      </div>
      <p className="mt-2 text-[12px] text-ink-tertiary">{desc}</p>
    </button>
  )
}

function RecommendJobCard({ job }: { job: Job }) {
  const navigate = useNavigate()
  const toggleFav = useToggleFavorite()
  return (
    <div className="flex flex-col rounded-xl bg-surface p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/jobs/${job.id}`} className="text-[15px] font-semibold text-ink hover:text-brand transition-colors line-clamp-1">
            {job.title}
          </Link>
          <p className="mt-0.5 text-[13px] text-ink-secondary">
            {job.companyName} · {job.city}
          </p>
        </div>
        {job.highlyRecommended && <Pill tone="orange">高度推荐</Pill>}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px] text-ink-secondary">
        <Pill tone="gray">{job.type === 'internship' ? '实习' : job.type === 'campus' ? '校招' : '全职'}</Pill>
        <span>届别 <MatchBadge level={job.gradYearMatch} /></span>
        <span>能力 <MatchBadge level={job.abilityMatch} /></span>
        <span className="inline-flex items-center gap-1.5">难度 <DifficultyMeter value={job.difficulty} /></span>
      </div>
      <p className="mt-3 flex-1 text-[13px] leading-relaxed text-ink-body">{job.recommendReason}</p>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-[12px] text-ink-tertiary">更新于 {job.lastUpdatedAt.slice(5, 16)}</span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className={cn('text-ink-secondary', job.isFavorite && 'text-highlight')}
            onClick={() => {
              toggleFav.mutate(job.id)
              toast.success(job.isFavorite ? '已取消收藏' : '岗位已收藏')
            }}
          >
            <Star className={cn('size-4', job.isFavorite && 'fill-current')} />
            {job.isFavorite ? '已收藏' : '收藏'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => navigate(`/jobs/${job.id}`)}>
            查看详情
          </Button>
        </div>
      </div>
    </div>
  )
}

const CHANGE_ICON = {
  discovered: <CheckCircle2 className="size-4 text-success" />,
  jd_updated: <Clock className="size-4 text-brand" />,
  entry_changed: <AlertTriangle className="size-4 text-warning" />,
  apply_changed: <AlertTriangle className="size-4 text-warning" />,
  closed: <MinusCircle className="size-4 text-ink-tertiary" />,
} as const

export default function DashboardPage() {
  const navigate = useNavigate()
  const { data: stats, isLoading, isError, refetch } = useDashboardStats()
  const { data: recommended } = useJobs({ tab: 'recommended' })
  const { data: allJobs } = useJobs({ tab: 'all' })
  const { data: runs } = useRuns()
  const { data: companies } = useCompanies()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [scope, setScope] = useState<'all' | 'failed'>('all')
  const [noEmail, setNoEmail] = useState(true)
  const [startingScan, setStartingScan] = useState(false)

  const startScan = async () => {
    setStartingScan(true)
    try {
      const result = await createRun({ scope, sendEmail: !noEmail })
      setDialogOpen(false)
      toast.success('真实扫描任务已创建', {
        description: scope === 'all' ? '正在扫描全部启用企业。' : '正在重试最近任务中的失败企业。',
      })
      navigate(`/runs/${result.runId}`)
    } catch (error) {
      toast.error('创建扫描任务失败', {
        description: error instanceof Error ? error.message : '请确认本地 API 正常运行。',
      })
    } finally {
      setStartingScan(false)
    }
  }

  const lastRun = runs?.[0]
  const companyProgress = useMemo(() => {
    if (!lastRun || !companies) return []
    return lastRun.companies.slice(0, 6).map((cr) => ({
      ...cr,
      companyStatus: companies.find((c) => c.id === cr.companyId)?.status,
    }))
  }, [lastRun, companies])
  const recentJobChanges = useMemo(
    () =>
      (allJobs ?? [])
        .flatMap((job) => job.history.map((change) => ({ ...change, jobId: job.id })))
        .sort((a, b) => b.time.localeCompare(a.time))
        .slice(0, 5),
    [allJobs],
  )

  if (isLoading) return <PageSkeleton />
  if (isError || !stats) return <ErrorState onRetry={() => refetch()} />

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <div className="relative overflow-hidden rounded-2xl bg-surface p-6 md:p-8 shadow-card">
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(600px 200px at 15% 0%, rgba(22,119,255,0.06), transparent 70%)' }}
        />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-[26px] md:text-[32px] font-semibold text-ink tracking-tight">
              {greeting()}，今天有 {stats.todayNew} 个新机会
            </h1>
            <p className="mt-2 text-[15px] text-ink-secondary">
              Career Radar 已为你监控 {stats.monitoredCompanies} 家企业，上次扫描完成于 {stats.lastScanAt}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/runs')}>
              <History className="size-4" />
              查看运行记录
            </Button>
            <Button
              onClick={() => setDialogOpen(true)}
              disabled={startingScan}
              className="bg-brand hover:bg-brand-hover text-white min-w-[132px]"
            >
              {startingScan ? (
                <span className="flex items-center gap-2">
                  <span className="size-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                  正在创建任务…
                </span>
              ) : (
                <>
                  <Play className="size-4" />
                  立即扫描
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* 关键数据 */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="今日新增岗位" value={stats.todayNew} delta={stats.todayNewDelta} desc="来自企业官网招聘页面" to="/jobs?tab=new" />
        <StatCard label="今日更新岗位" value={stats.todayUpdated} delta={stats.todayUpdatedDelta} desc="JD 或投递入口发生变化" to="/jobs?tab=updated" />
        <StatCard label="高匹配岗位" value={stats.highMatch} delta={stats.highMatchDelta} desc="与你当前画像匹配度高" to="/jobs?tab=recommended" />
        <StatCard label="监控企业" value={stats.monitoredCompanies} desc={`${stats.environment.successCompanies} 家正常 · ${stats.environment.pendingCompanies} 家待验证`} to="/companies" />
      </div>

      {/* AI 推荐岗位 */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[20px] font-semibold text-ink">最适合你的岗位</h2>
          <Link to="/jobs?tab=recommended" className="flex items-center text-[13px] text-brand hover:underline">
            查看全部
            <ChevronRight className="size-4" />
          </Link>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(recommended ?? []).slice(0, 3).map((job) => (
            <RecommendJobCard key={job.id} job={job} />
          ))}
        </div>
      </div>

      {/* 第三行：最近变化 + 运行状态 */}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle
            extra={
              <Link to="/jobs?tab=updated" className="flex items-center text-[13px] text-brand hover:underline">
                查看全部
                <ChevronRight className="size-4" />
              </Link>
            }
          >
            最近岗位变化
          </CardTitle>
          <ul className="divide-y divide-black/[0.05]">
            {recentJobChanges.map((c) => (
              <li key={`${c.jobId}-${c.time}`} className="flex items-center gap-3 py-3">
                {CHANGE_ICON[c.type]}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] text-ink-body">{c.summary}</p>
                  <p className="text-[12px] text-ink-tertiary">{c.time}</p>
                </div>
                <Button variant="ghost" size="sm" className="text-brand" onClick={() => navigate(`/jobs/${c.jobId}`)}>
                  查看变化
                </Button>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardTitle
            extra={
              lastRun && (
                <Link to={`/runs/${lastRun.id}`} className="flex items-center text-[13px] text-brand hover:underline">
                  运行详情
                  <ChevronRight className="size-4" />
                </Link>
              )
            }
          >
            最近一次扫描
          </CardTitle>
          {lastRun ? (
            <>
              <div className="grid grid-cols-3 gap-3 rounded-lg bg-surface-subtle p-4 text-center sm:grid-cols-6">
                {[
                  { label: '开始', value: lastRun.startedAt.slice(11, 16) },
                  { label: '耗时', value: `${Math.round(lastRun.durationMs / 1000)}s` },
                  { label: '成功', value: lastRun.successCount },
                  { label: '跳过', value: lastRun.skippedCount },
                  { label: '失败', value: lastRun.failedCount },
                  { label: '新增/更新', value: `${lastRun.newJobs}/${lastRun.updatedJobs}` },
                ].map((s) => (
                  <div key={s.label}>
                    <p className="text-[16px] font-semibold text-ink tabular-nums">{s.value}</p>
                    <p className="text-[11px] text-ink-tertiary">{s.label}</p>
                  </div>
                ))}
              </div>
              <ul className="mt-4 space-y-2">
                {companyProgress.map((c) => (
                  <li key={c.companyId} className="flex items-center justify-between text-[13px]">
                    <span className="text-ink-body">{c.companyName}</span>
                    {c.status === 'success' ? (
                      <Pill tone="green">成功{c.newJobs + c.updatedJobs > 0 ? ` · +${c.newJobs}/↑${c.updatedJobs}` : ''}</Pill>
                    ) : c.status === 'failed' ? (
                      <Pill tone="red">失败</Pill>
                    ) : c.status === 'skipped' ? (
                      <Pill tone="gray">{c.companyStatus === 'robots_blocked' ? 'robots 禁止' : '已跳过'}</Pill>
                    ) : (
                      <Pill tone="amber">等待扫描</Pill>
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-[13px] text-ink-secondary">暂无运行记录</p>
          )}
        </Card>
      </div>

      {/* 需要关注 */}
      <Card>
        <CardTitle>需要关注</CardTitle>
        <ul className="space-y-3">
          {stats.attentionItems.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-surface-subtle px-4 py-3"
            >
              <div className="flex items-center gap-3">
                {item.kind === 'company_failed' ? (
                  <XCircle className="size-4 text-danger shrink-0" />
                ) : (
                  <AlertTriangle className="size-4 text-warning shrink-0" />
                )}
                <span className="text-[14px] text-ink-body">{item.text}</span>
              </div>
              <Button variant="outline" size="sm" onClick={() => navigate(item.link)}>
                {item.actionLabel}
                <ArrowUpRight className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      {/* 扫描确认弹窗 */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="rounded-xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-ink">开始扫描</DialogTitle>
            <DialogDescription>扫描会依次访问企业官网的公开招聘页面，全程遵循 robots.txt 与请求间隔限制。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <RadioGroup value={scope} onValueChange={(v) => setScope(v as 'all' | 'failed')} className="space-y-2">
              <div className="flex items-center gap-2.5 rounded-lg border border-black/[0.08] px-3 py-2.5">
                <RadioGroupItem value="all" id="scope-all" />
                <Label htmlFor="scope-all" className="flex-1 cursor-pointer">
                  扫描全部企业
                  <span className="block text-[12px] text-ink-tertiary">共 {stats.monitoredCompanies} 家，预计 2~4 分钟</span>
                </Label>
              </div>
              <div className="flex items-center gap-2.5 rounded-lg border border-black/[0.08] px-3 py-2.5">
                <RadioGroupItem value="failed" id="scope-failed" />
                <Label htmlFor="scope-failed" className="flex-1 cursor-pointer">
                  仅扫描失败企业
                  <span className="block text-[12px] text-ink-tertiary">SmartX 等抓取失败的企业</span>
                </Label>
              </div>
            </RadioGroup>
            <div className="flex items-center gap-2.5">
              <Checkbox id="no-email" checked={noEmail} onCheckedChange={(v) => setNoEmail(v === true)} />
              <Label htmlFor="no-email" className="cursor-pointer text-[13px]">
                本次不发送邮件（仅生成日报）
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              className="bg-brand hover:bg-brand-hover text-white"
              onClick={startScan}
              disabled={startingScan}
            >
              {startingScan ? '正在创建…' : '开始扫描'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
