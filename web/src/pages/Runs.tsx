import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Plus, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Progress } from '@/components/ui/progress'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { RunStatusBadge, EmailStatusBadge } from '@/components/common/Badges'
import { ListSkeleton, EmptyState, ErrorState } from '@/components/common/StateViews'
import { useRuns } from '@/hooks/useData'
import { createRun } from '@/services/runs'

const TRIGGER_LABEL: Record<string, string> = {
  manual: '手动触发',
  scheduled: '定时任务',
  retry: '失败重试',
}

export default function RunsPage() {
  const navigate = useNavigate()
  const { data: runs, isLoading, isError, refetch } = useRuns()
  const [creating, setCreating] = useState(false)

  const startRun = async () => {
    setCreating(true)
    try {
      const result = await createRun({ scope: 'all', sendEmail: false })
      toast.success('真实扫描任务已创建')
      navigate(`/runs/${result.runId}`)
    } catch (error) {
      toast.error('创建任务失败', {
        description: error instanceof Error ? error.message : '请确认本地 API 正常运行。',
      })
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="运行中心"
        subtitle="每一次扫描任务的执行过程与结果"
        actions={
          <Button
            className="bg-brand hover:bg-brand-hover text-white"
            onClick={startRun}
            disabled={creating}
          >
            <Plus className="size-4" />
            {creating ? '正在创建…' : '新建扫描任务'}
          </Button>
        }
      />

      <Card padded={false}>
        {isLoading ? (
          <div className="p-4"><ListSkeleton rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : !runs || runs.length === 0 ? (
          <EmptyState
            icon={<Activity className="size-6" />}
            title="还没有运行记录"
            description="创建第一个扫描任务后，这里会记录每次执行的详细过程。"
            actions={
              <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => navigate('/')}>
                去总览发起扫描
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>任务编号</TableHead>
                  <TableHead>运行方式</TableHead>
                  <TableHead>开始时间</TableHead>
                  <TableHead>结束时间</TableHead>
                  <TableHead className="w-36">进度</TableHead>
                  <TableHead>成功 / 失败</TableHead>
                  <TableHead>新增 / 更新</TableHead>
                  <TableHead>邮件</TableHead>
                  <TableHead>任务状态</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((r) => {
                  const pct = Math.round((r.finishedCompanies / Math.max(1, r.totalCompanies)) * 100)
                  return (
                    <TableRow key={r.id} className="cursor-pointer" onClick={() => navigate(`/runs/${r.id}`)}>
                      <TableCell className="font-medium text-brand">{r.code}</TableCell>
                      <TableCell className="text-[13px] text-ink-body">{TRIGGER_LABEL[r.trigger]}</TableCell>
                      <TableCell className="text-[13px] text-ink-body tabular-nums">{r.startedAt}</TableCell>
                      <TableCell className="text-[13px] text-ink-body tabular-nums">{r.finishedAt ?? '—'}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Progress value={pct} className="h-1.5 w-20" />
                          <span className="text-[12px] text-ink-tertiary tabular-nums">{pct}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-[13px] tabular-nums">
                        <span className="text-success">{r.successCount}</span>
                        <span className="text-ink-tertiary"> / </span>
                        <span className={r.failedCount > 0 ? 'text-danger' : 'text-ink-body'}>{r.failedCount}</span>
                      </TableCell>
                      <TableCell className="text-[13px] tabular-nums text-ink-body">+{r.newJobs} / ↑{r.updatedJobs}</TableCell>
                      <TableCell><EmailStatusBadge status={r.emailStatus} /></TableCell>
                      <TableCell><RunStatusBadge status={r.status} /></TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </div>
  )
}
