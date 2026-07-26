import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Square,
  RotateCcw,
  Download,
  CheckCircle2,
  XCircle,
  MinusCircle,
  Clock,
  ChevronDown,
  ChevronRight,
  Search,
  Copy,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Card } from '@/components/common/PageHeader'
import { RunStatusBadge, EmailStatusBadge, Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState, EmptyState } from '@/components/common/StateViews'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useRun } from '@/hooks/useData'
import { stopRun, retryFailed } from '@/services/runs'
import { downloadTextFile } from '@/services/reports'
import type { StepStatus, CompanyRun, RunLog } from '@/types'
import { cn } from '@/lib/utils'
import { isActiveRunStatus } from '@/lib/runStatus'

function StepIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'success':
      return <CheckCircle2 className="size-4 text-success shrink-0" />
    case 'failed':
      return <XCircle className="size-4 text-danger shrink-0" />
    case 'skipped':
      return <MinusCircle className="size-4 text-ink-tertiary shrink-0" />
    case 'running':
      return <Loader2 className="size-4 text-brand animate-spin shrink-0" />
    default:
      return <Clock className="size-4 text-ink-tertiary/50 shrink-0" />
  }
}

function CompanyRunCard({ cr, defaultOpen }: { cr: CompanyRun; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="rounded-xl border border-black/[0.06] bg-surface">
        <CollapsibleTrigger className="flex w-full items-center gap-3 px-4 py-3.5 text-left">
          {open ? <ChevronDown className="size-4 text-ink-tertiary" /> : <ChevronRight className="size-4 text-ink-tertiary" />}
          <span className="text-[14px] font-medium text-ink">{cr.companyName}</span>
          {cr.newJobs + cr.updatedJobs > 0 && (
            <Pill tone="green">+{cr.newJobs} 新增 / ↑{cr.updatedJobs} 更新</Pill>
          )}
          <span className="ml-auto">
            {cr.status === 'success' ? (
              <Pill tone="green">成功</Pill>
            ) : cr.status === 'failed' ? (
              <Pill tone="red">失败</Pill>
            ) : cr.status === 'skipped' ? (
              <Pill tone="gray">跳过</Pill>
            ) : cr.status === 'running' ? (
              <Pill tone="blue">进行中</Pill>
            ) : (
              <Pill tone="amber">等待</Pill>
            )}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="border-t border-black/[0.05] px-4 py-3">
            {cr.error && (
              <p className="mb-3 rounded-lg bg-danger-soft px-3 py-2 text-[12px] text-danger">{cr.error}</p>
            )}
            <div className="mb-3 grid gap-2 rounded-lg bg-black/[0.025] px-3 py-2 text-[12px] text-ink-secondary sm:grid-cols-3">
              <span>已访问：<b className="text-ink">{cr.pagesVisited ?? 0}</b> 页</span>
              <span>成功 / 失败：<b className="text-ink">{cr.successfulPages ?? 0} / {cr.failedPages ?? 0}</b></span>
              <span>已提取岗位：<b className="text-ink">{cr.jobsSeen ?? 0}</b></span>
              {cr.currentPage && (
                <span className="min-w-0 sm:col-span-3">
                  当前页面：<span className="break-all font-mono text-[11px] text-ink-tertiary">{cr.currentPage}</span>
                </span>
              )}
            </div>
            <ol className="space-y-2">
              {cr.steps.map((s) => (
                <li key={s.key} className="flex items-center gap-3 text-[13px]">
                  <StepIcon status={s.status} />
                  <span className={cn('w-28 shrink-0', s.status === 'waiting' ? 'text-ink-tertiary/60' : 'text-ink-body')}>
                    {s.label}
                  </span>
                  <span className={cn('flex-1', s.status === 'waiting' ? 'text-ink-tertiary/60' : 'text-ink-secondary')}>
                    {s.message}
                  </span>
                  <span className="shrink-0 text-[12px] text-ink-tertiary tabular-nums">
                    {s.durationMs !== undefined ? `${(s.durationMs / 1000).toFixed(1)}s` : '—'}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

function LogLine({ log }: { log: RunLog }) {
  return (
    <div className="flex gap-3 py-1 font-mono text-[12px] leading-relaxed">
      <span className="shrink-0 text-ink-tertiary tabular-nums">{log.time.slice(11)}</span>
      <span
        className={cn(
          'shrink-0 w-11',
          log.level === 'ERROR' ? 'text-danger' : log.level === 'WARN' ? 'text-warning' : 'text-ink-tertiary',
        )}
      >
        {log.level}
      </span>
      <span className="text-ink-body">
        {log.company && <span className="text-brand-foreground">[{log.company}] </span>}
        {log.message}
      </span>
    </div>
  )
}

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: run, isLoading, isError, refetch } = useRun(id ?? '')
  const [stopOpen, setStopOpen] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [logQuery, setLogQuery] = useState('')
  const [logLevel, setLogLevel] = useState<'all' | 'WARN' | 'ERROR'>('all')

  const filteredLogs = useMemo(() => {
    if (!run) return []
    return run.logs.filter((l) => {
      if (logLevel !== 'all' && l.level !== logLevel) return false
      if (logQuery && ![l.message, l.company ?? '', l.level].join(' ').toLowerCase().includes(logQuery.toLowerCase()))
        return false
      return true
    })
  }, [run, logQuery, logLevel])

  if (isLoading) return <PageSkeleton />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!run)
    return (
      <EmptyState
        title="没有找到这个任务"
        actions={<Button variant="outline" onClick={() => navigate('/runs')}>返回运行中心</Button>}
      />
    )

  const pct = Math.round((run.finishedCompanies / Math.max(1, run.totalCompanies)) * 100)
  const running = isActiveRunStatus(run.status)
  const hasFailed = run.companies.some((c) => c.status === 'failed')

  return (
    <div className="space-y-5">
      <Link to="/runs" className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors">
        <ArrowLeft className="size-4" />
        返回运行中心
      </Link>

      {/* 任务概要 */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[22px] font-semibold text-ink">{run.code}</h1>
              <RunStatusBadge status={run.status} />
              <EmailStatusBadge status={run.emailStatus} />
            </div>
            <p className="mt-1.5 text-[13px] text-ink-secondary">
              {run.status === 'stopping'
                ? `停止请求已提交，正在等待当前 HTTP/LLM 调用返回；已完成 ${run.finishedCompanies} / ${run.totalCompanies} 家企业`
                : running
                ? `正在扫描 ${run.companies.find((c) => c.status === 'running')?.companyName ?? ''}，已完成 ${run.finishedCompanies} / ${run.totalCompanies} 家企业`
                : `${run.startedAt} 开始 · ${run.finishedAt ?? '—'} 结束 · 总耗时 ${Math.round(run.durationMs / 1000)} 秒`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {running && run.canStop && (
              <Button variant="outline" className="text-danger border-danger/30 hover:bg-danger-soft" onClick={() => setStopOpen(true)}>
                <Square className="size-4" />
                停止任务
              </Button>
            )}
            {hasFailed && (
              <Button
                variant="outline"
                onClick={async () => {
                  try {
                    const result = await retryFailed(run.id)
                    toast.success('已创建失败企业重试任务')
                    if (result.runId) navigate(`/runs/${result.runId}`)
                  } catch (error) {
                    toast.error('创建重试任务失败', {
                      description: error instanceof Error ? error.message : '请稍后重试。',
                    })
                  }
                }}
              >
                <RotateCcw className="size-4" />
                仅重试失败企业
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => {
                downloadTextFile(
                  `${run.code}.log`,
                  run.logs.map((l) => `${l.time} [${l.level}] ${l.company ? `[${l.company}] ` : ''}${l.message}`).join('\n'),
                  'text/plain',
                )
                toast.success('日志已下载')
              }}
            >
              <Download className="size-4" />
              下载日志
            </Button>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Progress value={pct} className="h-2 flex-1" />
          <span className="text-[13px] text-ink-secondary tabular-nums">{run.finishedCompanies} / {run.totalCompanies} 家 · {pct}%</span>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
          {[
            { label: '成功企业', value: run.successCount, cls: 'text-success' },
            { label: '跳过', value: run.skippedCount, cls: 'text-ink-secondary' },
            { label: '失败', value: run.failedCount, cls: run.failedCount > 0 ? 'text-danger' : 'text-ink' },
            { label: '新增岗位', value: run.newJobs, cls: 'text-ink' },
            { label: '更新岗位', value: run.updatedJobs, cls: 'text-ink' },
          ].map((s) => (
            <div key={s.label} className="rounded-lg bg-surface-subtle p-3 text-center">
              <p className={cn('text-[20px] font-semibold tabular-nums', s.cls)}>{s.value}</p>
              <p className="text-[12px] text-ink-tertiary">{s.label}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* 企业执行过程 */}
      <div className="space-y-3">
        <h2 className="text-[18px] font-semibold text-ink">企业执行过程</h2>
        {run.companies.map((cr) => (
          <CompanyRunCard key={cr.companyId} cr={cr} defaultOpen={cr.status === 'failed'} />
        ))}
      </div>

      {/* 技术日志折叠区 */}
      <Card padded={false}>
        <Collapsible open={logOpen} onOpenChange={setLogOpen}>
          <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-4">
            <span className="text-[15px] font-semibold text-ink">技术日志（{run.logs.length} 条）</span>
            <ChevronDown className={cn('size-4 text-ink-tertiary transition-transform', logOpen && 'rotate-180')} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="border-t border-black/[0.05] px-6 py-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <div className="relative flex-1 min-w-52">
                  <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
                  <Input
                    value={logQuery}
                    onChange={(e) => setLogQuery(e.target.value)}
                    placeholder="搜索日志内容或企业名…"
                    className="h-9 pl-9 rounded-lg bg-surface-subtle border-black/[0.06]"
                  />
                </div>
                <div className="flex items-center gap-1.5 text-[12px]">
                  {(['all', 'WARN', 'ERROR'] as const).map((lv) => (
                    <button
                      key={lv}
                      onClick={() => setLogLevel(lv)}
                      className={cn(
                        'rounded-md px-2.5 py-1.5 transition-colors',
                        logLevel === lv ? 'bg-ink text-white' : 'text-ink-secondary hover:bg-black/[0.04]',
                      )}
                    >
                      {lv === 'all' ? '全部' : lv}
                    </button>
                  ))}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(filteredLogs.map((l) => `${l.time} [${l.level}] ${l.message}`).join('\n'))
                    toast.success('日志已复制到剪贴板')
                  }}
                >
                  <Copy className="size-3.5" />
                  复制
                </Button>
              </div>
              <div className="max-h-80 overflow-auto rounded-lg bg-surface-subtle p-4 scrollbar-thin">
                {filteredLogs.length === 0 ? (
                  <p className="py-4 text-center text-[13px] text-ink-tertiary">没有匹配的日志。</p>
                ) : (
                  filteredLogs.map((l, i) => <LogLine key={i} log={l} />)
                )}
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      <ConfirmDialog
        open={stopOpen}
        onOpenChange={setStopOpen}
        title="停止当前任务？"
        description="停止请求不会强杀当前 HTTP/LLM 调用；调用返回后会在最近安全点停止。已完成企业的入库结果会保留，未扫描企业本次不再执行。"
        confirmLabel="停止任务"
        destructive
        onConfirm={async () => {
          try {
            await stopRun(run.id)
            toast.success('已提交停止请求')
            setStopOpen(false)
            refetch()
          } catch (error) {
            toast.error('无法停止任务', {
              description: error instanceof Error ? error.message : '当前任务不支持安全停止。',
            })
          }
        }}
      />
    </div>
  )
}
