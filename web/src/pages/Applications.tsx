import { Link } from 'react-router'
import { AlertTriangle, FileUser, LockKeyhole, Sparkles } from 'lucide-react'
import { Progress } from '@/components/ui/progress'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/common/StateViews'
import { Pill } from '@/components/common/Badges'
import { useApplicationProfileStatus, useApplications } from '@/hooks/useApplications'
import { APPLICATION_STATUS_LABEL } from '@/types'
import type { ApplicationStatus } from '@/types'

function statusTone(status: ApplicationStatus): 'green' | 'red' | 'amber' | 'blue' | 'gray' {
  if (status === 'ready') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'waiting_for_approval') return 'amber'
  if (status === 'rejected') return 'gray'
  return 'blue'
}

export default function ApplicationsPage() {
  const { data: profile } = useApplicationProfileStatus()
  const { data: tasks, isLoading, isError, refetch } = useApplications()

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI 申请材料"
        subtitle="岗位评估、人工批准、简历定制、求职信和双重审查"
      />

      <div
        className={`flex items-start gap-3 rounded-xl px-4 py-3 text-[13px] ${
          profile?.ready ? 'bg-success-soft text-success' : 'bg-warning-soft text-warning'
        }`}
      >
        {profile?.ready ? <LockKeyhole className="mt-0.5 size-4 shrink-0" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0" />}
        <div>
          <p className="font-medium">{profile?.ready ? '私有申请画像已确认' : '申请画像尚未就绪'}</p>
          <p className="mt-0.5 opacity-80">
            {profile?.ready
              ? '画像仅保存在本机，列表和 API 不会返回姓名、电话、邮箱或绝对文件路径。'
              : profile?.message || '请先在本机完成私有画像配置和确认。'}
          </p>
        </div>
      </div>

      {isLoading ? (
        <Card><ListSkeleton rows={5} /></Card>
      ) : isError ? (
        <Card><ErrorState onRetry={() => refetch()} /></Card>
      ) : !tasks?.length ? (
        <Card>
          <EmptyState
            icon={<FileUser className="size-6" />}
            title="还没有申请材料任务"
            description="打开一个 JD 完整的具体岗位，在岗位详情中点击“AI 定制申请材料”。"
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <Link key={task.id} to={`/applications/${task.id}`} className="block">
              <Card className="transition hover:-translate-y-0.5 hover:shadow-md">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Sparkles className="size-4 text-brand" />
                      <h2 className="text-[16px] font-semibold text-ink">
                        {task.job?.title || '岗位快照不可用'}
                      </h2>
                      <Pill tone={statusTone(task.status)}>{APPLICATION_STATUS_LABEL[task.status]}</Pill>
                    </div>
                    <p className="mt-1 text-[13px] text-ink-secondary">
                      {task.job?.company || '未知企业'}{task.job?.location ? ` · ${task.job.location}` : ''}
                    </p>
                    <p className="mt-2 text-[12px] text-ink-tertiary">
                      创建于 {task.createdAt} · {task.nextAction}
                    </p>
                  </div>
                  {task.evaluation && (
                    <div className="text-right">
                      <p className="text-[24px] font-semibold text-brand tabular-nums">{task.evaluation.overall_score}</p>
                      <p className="text-[11px] text-ink-tertiary">岗位匹配分</p>
                    </div>
                  )}
                </div>
                <div className="mt-4 flex items-center gap-3">
                  <Progress value={task.progress} className="h-1.5 flex-1" />
                  <span className="text-[12px] tabular-nums text-ink-tertiary">{task.progress}%</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
