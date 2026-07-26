import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  ArrowLeft,
  BookOpen,
  Table2,
  Download,
  FileSpreadsheet,
  Sparkles,
  AlertTriangle,
  Compass,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { MatchBadge, JobStatusBadge, DifficultyMeter, Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState, EmptyState } from '@/components/common/StateViews'
import { useReport } from '@/hooks/useData'
import { useJobs } from '@/hooks/useJobs'
import { downloadReport } from '@/services/reports'
import { JOB_TYPE_LABEL } from '@/types'
import type { Job } from '@/types'

function JobLine({ job, highlight }: { job: Job; highlight?: boolean }) {
  return (
    <li>
      <Link to={`/jobs/${job.id}`} className="flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 hover:bg-black/[0.03] transition-colors">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-[14px] font-medium text-ink">
            <span className="truncate">{job.title}</span>
            {highlight && <Pill tone="orange">高度推荐</Pill>}
          </p>
          <p className="text-[12px] text-ink-tertiary">
            {job.companyName} · {job.city} · {JOB_TYPE_LABEL[job.type]} · 难度 {job.difficulty}/10
          </p>
        </div>
        <MatchBadge level={job.abilityMatch} />
      </Link>
    </li>
  )
}

export default function ReportDetailPage() {
  const { date } = useParams<{ date: string }>()
  const navigate = useNavigate()
  const { data: report, isLoading, isError, refetch } = useReport(date ?? '')
  const { data: allJobs } = useJobs({ tab: 'all' })
  const [mode, setMode] = useState<'read' | 'table'>('read')

  if (isLoading) return <PageSkeleton />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!report)
    return (
      <EmptyState
        title="没有找到这天的日报"
        description="日报可能尚未生成，或日期有误。"
        actions={<Button variant="outline" onClick={() => navigate('/reports')}>返回日报中心</Button>}
      />
    )

  const jobById = (id: string) => (allJobs ?? []).find((j) => j.id === id)
  const topJobs = report.topJobIds.map(jobById).filter((j): j is Job => !!j)
  const newJobs = report.newJobIds.map(jobById).filter((j): j is Job => !!j)
  const updatedJobs = report.updatedJobIds.map(jobById).filter((j): j is Job => !!j)
  const tableJobs = [...newJobs, ...updatedJobs]

  return (
    <div className="space-y-5">
      <Link to="/reports" className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors">
        <ArrowLeft className="size-4" />
        返回日报中心
      </Link>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-semibold text-ink">{report.date} 求职日报</h1>
            <p className="mt-1 text-[13px] text-ink-secondary">
              新增 {report.newJobs} · 更新 {report.updatedJobs} · 高匹配 {report.highMatchJobs}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Tabs value={mode} onValueChange={(v) => setMode(v as 'read' | 'table')}>
              <TabsList className="rounded-lg">
                <TabsTrigger value="read" className="rounded-md">
                  <BookOpen className="size-4" />
                  阅读模式
                </TabsTrigger>
                <TabsTrigger value="table" className="rounded-md">
                  <Table2 className="size-4" />
                  数据表模式
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <Button
              variant="outline"
              onClick={async () => { await downloadReport(report.date, 'md'); toast.success('Markdown 日报已下载') }}
            >
              <Download className="size-4" />
              下载 Markdown
            </Button>
            <div className="flex flex-col items-start">
              <Button
                variant="outline"
                onClick={async () => { await downloadReport(report.date, 'csv'); toast.success('CSV 日报已下载') }}
              >
                <FileSpreadsheet className="size-4" />
                下载 CSV
              </Button>
              <span className="mt-1 text-[11px] text-ink-tertiary">文件使用 UTF-8 BOM，可直接使用 Excel 打开。</span>
            </div>
          </div>
        </div>
      </Card>

      {mode === 'read' ? (
        <div className="space-y-5">
          <Card>
            <CardTitle>今日摘要</CardTitle>
            <p className="text-[14px] leading-relaxed text-ink-body">{report.summary}</p>
          </Card>

          {topJobs.length > 0 && (
            <Card>
              <CardTitle
                extra={
                  <span className="flex items-center gap-1 text-[12px] text-highlight">
                    <Sparkles className="size-3.5" />
                    按当前画像匹配
                  </span>
                }
              >
                最推荐岗位
              </CardTitle>
              <ul className="space-y-1">
                {topJobs.map((j) => (
                  <JobLine key={j.id} job={j} highlight />
                ))}
              </ul>
            </Card>
          )}

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <CardTitle>新增岗位（{newJobs.length}）</CardTitle>
              {newJobs.length === 0 ? (
                <p className="text-[13px] text-ink-tertiary">今日无新增岗位。</p>
              ) : (
                <ul className="space-y-1">{newJobs.map((j) => <JobLine key={j.id} job={j} />)}</ul>
              )}
            </Card>
            <Card>
              <CardTitle>更新岗位（{updatedJobs.length}）</CardTitle>
              {updatedJobs.length === 0 ? (
                <p className="text-[13px] text-ink-tertiary">今日无岗位更新。</p>
              ) : (
                <ul className="space-y-1">{updatedJobs.map((j) => <JobLine key={j.id} job={j} />)}</ul>
              )}
            </Card>
          </div>

          {report.anomalies.length > 0 && (
            <Card>
              <CardTitle>企业扫描异常</CardTitle>
              <ul className="space-y-2">
                {report.anomalies.map((a, i) => (
                  <li key={i} className="flex items-start gap-2.5 rounded-lg bg-warning-soft px-3.5 py-2.5 text-[13px] text-warning">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    {a}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {report.tomorrowFocus.length > 0 && (
            <Card>
              <CardTitle
                extra={<Compass className="size-4 text-ink-tertiary" />}
              >
                明日关注建议
              </CardTitle>
              <ul className="space-y-2">
                {report.tomorrowFocus.map((t, i) => (
                  <li key={i} className="flex gap-2.5 text-[14px] text-ink-body">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[11px] font-medium text-brand-foreground">
                      {i + 1}
                    </span>
                    {t}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      ) : (
        <Card padded={false}>
          {tableJobs.length === 0 ? (
            <EmptyState title="这天没有岗位记录" />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>职位名称</TableHead>
                    <TableHead>企业</TableHead>
                    <TableHead>城市</TableHead>
                    <TableHead>类型</TableHead>
                    <TableHead>变化</TableHead>
                    <TableHead>届别匹配</TableHead>
                    <TableHead>能力匹配</TableHead>
                    <TableHead>难度</TableHead>
                    <TableHead>投递链接</TableHead>
                    <TableHead>更新时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tableJobs.map((j) => (
                    <TableRow key={j.id} className="cursor-pointer" onClick={() => navigate(`/jobs/${j.id}`)}>
                      <TableCell className="max-w-[220px] truncate font-medium text-ink">{j.title}</TableCell>
                      <TableCell className="text-[13px]">{j.companyName}</TableCell>
                      <TableCell className="text-[13px]">{j.city}</TableCell>
                      <TableCell className="text-[13px]">{JOB_TYPE_LABEL[j.type]}</TableCell>
                      <TableCell><JobStatusBadge status={j.status} /></TableCell>
                      <TableCell><MatchBadge level={j.gradYearMatch} /></TableCell>
                      <TableCell><MatchBadge level={j.abilityMatch} /></TableCell>
                      <TableCell><DifficultyMeter value={j.difficulty} /></TableCell>
                      <TableCell className="text-[13px]">{j.hasApplyUrl ? '有' : '无'}</TableCell>
                      <TableCell className="text-[12px] text-ink-tertiary tabular-nums">{j.lastUpdatedAt}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
