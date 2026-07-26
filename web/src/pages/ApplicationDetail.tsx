import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { PageHeader, Card, CardTitle } from '@/components/common/PageHeader'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { EmptyState, ErrorState, PageSkeleton } from '@/components/common/StateViews'
import { Pill } from '@/components/common/Badges'
import {
  useApplication,
  useApproveApplication,
  useRejectApplication,
  useRenderApplication,
  useResumeApplication,
} from '@/hooks/useApplications'
import { downloadApplicationArtifact } from '@/services/applications'
import {
  APPLICATION_DIMENSION_LABEL,
  APPLICATION_STATUS_LABEL,
} from '@/types'
import type { ApplicationStatus } from '@/types'

const VERDICT_LABEL = {
  strong: '强烈建议申请',
  good: '建议申请',
  moderate: '可尝试申请',
  weak: '匹配较弱',
  ineligible: '不满足硬性条件',
} as const

function statusTone(status: ApplicationStatus): 'green' | 'red' | 'amber' | 'blue' | 'gray' {
  if (status === 'ready') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'waiting_for_approval') return 'amber'
  if (status === 'rejected') return 'gray'
  return 'blue'
}

function actionError(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请检查本地 API 和运行日志。'
}

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: task, isLoading, isError, refetch } = useApplication(id ?? '')
  const approve = useApproveApplication()
  const reject = useRejectApplication()
  const resume = useResumeApplication()
  const render = useRenderApplication()
  const [approveOpen, setApproveOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [downloading, setDownloading] = useState<string>()

  if (isLoading) return <PageSkeleton />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!task) {
    return (
      <EmptyState
        title="没有找到这个申请任务"
        actions={<Button variant="outline" onClick={() => navigate('/applications')}>返回申请材料</Button>}
      />
    )
  }

  const evaluation = task.evaluation
  const mutate = (
    operation: typeof approve | typeof reject | typeof resume | typeof render,
    successMessage: string,
  ) => operation.mutate(task.id, {
    onSuccess: () => toast.success(successMessage),
    onError: (error) => toast.error('操作失败', { description: actionError(error) }),
  })

  return (
    <div className="space-y-5">
      <Link to="/applications" className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink">
        <ArrowLeft className="size-4" />
        返回申请材料
      </Link>

      <PageHeader
        title={task.job?.title || '申请材料任务'}
        subtitle={`${task.job?.company || '未知企业'}${task.job?.location ? ` · ${task.job.location}` : ''}`}
        actions={
          <Button asChild variant="outline">
            <Link to={`/jobs/${task.jobId}`}>查看岗位详情</Link>
          </Button>
        }
      />

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="size-4 text-brand" />
              <Pill tone={statusTone(task.status)}>{APPLICATION_STATUS_LABEL[task.status]}</Pill>
              {task.isRunning && <Loader2 className="size-4 animate-spin text-brand" />}
            </div>
            <p className="mt-2 text-[14px] text-ink-body">{task.nextAction}</p>
            <p className="mt-1 text-[12px] text-ink-tertiary">最后更新 {task.updatedAt}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {task.canApprove && (
              <Button className="bg-brand text-white hover:bg-brand-hover" onClick={() => setApproveOpen(true)}>
                <CheckCircle2 className="size-4" />批准生成材料
              </Button>
            )}
            {task.canResume && (
              <Button onClick={() => mutate(resume, '已从失败步骤恢复')}>
                <RotateCcw className="size-4" />恢复任务
              </Button>
            )}
            {task.canRender && (
              <Button onClick={() => mutate(render, '已继续生成并校验文档')}>
                <FileText className="size-4" />继续生成文档
              </Button>
            )}
            {task.canReject && (
              <Button variant="outline" className="text-danger" onClick={() => setRejectOpen(true)}>
                放弃本次申请
              </Button>
            )}
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Progress value={task.progress} className="h-2 flex-1" />
          <span className="text-[13px] text-ink-secondary tabular-nums">{task.progress}%</span>
        </div>
        {task.status === 'failed' && (
          <div className="mt-4 flex items-start gap-2 rounded-lg bg-danger-soft px-3 py-2 text-[13px] text-danger">
            <XCircle className="mt-0.5 size-4 shrink-0" />
            {task.error || '任务执行失败。隐私保护已隐藏原始异常，请在本机日志中查看原因。'}
          </div>
        )}
      </Card>

      {evaluation ? (
        <>
          <Card>
            <CardTitle>岗位匹配结论</CardTitle>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg bg-brand-soft p-4 text-center">
                <p className="text-[30px] font-semibold text-brand tabular-nums">{evaluation.overall_score}</p>
                <p className="text-[12px] text-brand-foreground">综合匹配分 / 100</p>
              </div>
              <div className="rounded-lg bg-warning-soft p-4 text-center">
                <p className="text-[30px] font-semibold text-warning tabular-nums">{evaluation.difficulty_score}</p>
                <p className="text-[12px] text-warning">申请难度 / 10</p>
              </div>
              <div className="rounded-lg bg-surface-subtle p-4 text-center">
                <p className="mt-1 text-[17px] font-semibold text-ink">{VERDICT_LABEL[evaluation.verdict]}</p>
                <p className="mt-2 text-[12px] text-ink-tertiary">DeepSeek 结构化评估</p>
              </div>
            </div>
            <p className="mt-4 rounded-lg bg-surface-subtle px-4 py-3 text-[14px] leading-relaxed text-ink-body">
              {evaluation.recommendation}
            </p>
          </Card>

          <Card>
            <CardTitle>五维匹配分析</CardTitle>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {evaluation.dimensions.map((dimension) => (
                <div key={dimension.name} className="rounded-lg border border-black/[0.06] p-4">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink">{APPLICATION_DIMENSION_LABEL[dimension.name]}</p>
                    <span className="text-[16px] font-semibold text-brand tabular-nums">{dimension.score}</span>
                  </div>
                  <Progress value={dimension.score} className="mt-2 h-1.5" />
                  <p className="mt-3 text-[11px] text-ink-tertiary">权重 {dimension.weight}%</p>
                  {dimension.strengths.length > 0 && (
                    <p className="mt-2 text-[12px] leading-relaxed text-success">优势：{dimension.strengths.join('；')}</p>
                  )}
                  {dimension.gaps.length > 0 && (
                    <p className="mt-1 text-[12px] leading-relaxed text-warning">差距：{dimension.gaps.join('；')}</p>
                  )}
                </div>
              ))}
            </div>
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card>
              <CardTitle>硬性资格检查</CardTitle>
              <div className="space-y-3">
                {evaluation.eligibility.length ? evaluation.eligibility.map((item) => (
                  <div key={item.name} className="rounded-lg bg-surface-subtle p-3">
                    <div className="flex items-center gap-2">
                      {item.verdict === 'pass' ? (
                        <CheckCircle2 className="size-4 text-success" />
                      ) : item.verdict === 'fail' ? (
                        <XCircle className="size-4 text-danger" />
                      ) : (
                        <AlertTriangle className="size-4 text-warning" />
                      )}
                      <p className="text-[13px] font-medium text-ink">{item.name}</p>
                    </div>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-ink-secondary">{item.reason}</p>
                  </div>
                )) : <p className="text-[13px] text-ink-tertiary">JD 没有可核验的硬性条件。</p>}
              </div>
            </Card>

            <Card>
              <CardTitle>JD 要求覆盖</CardTitle>
              <div className="space-y-3">
                {evaluation.requirement_coverage.length ? evaluation.requirement_coverage.map((item, index) => (
                  <div key={`${item.requirement}-${index}`} className="rounded-lg bg-surface-subtle p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[13px] font-medium leading-relaxed text-ink">{item.requirement}</p>
                      <Pill tone={item.status === 'matched' ? 'green' : item.status === 'gap' ? 'red' : 'amber'}>
                        {item.status === 'matched' ? '已覆盖' : item.status === 'partial' ? '部分覆盖' : item.status === 'gap' ? '存在差距' : '未知'}
                      </Pill>
                    </div>
                    {item.candidate_evidence.length > 0 && (
                      <p className="mt-1.5 text-[12px] leading-relaxed text-ink-secondary">
                        画像证据：{item.candidate_evidence.join('；')}
                      </p>
                    )}
                    {item.honest_bridge && <p className="mt-1 text-[12px] text-warning">诚实补位：{item.honest_bridge}</p>}
                  </div>
                )) : <p className="text-[13px] text-ink-tertiary">暂无逐项要求覆盖结果。</p>}
              </div>
            </Card>
          </div>
        </>
      ) : (
        <Card>
          <div className="flex items-center gap-3 text-[13px] text-ink-secondary">
            <Loader2 className="size-4 animate-spin text-brand" />
            DeepSeek 尚未完成岗位与私有画像的结构化评估。
          </div>
        </Card>
      )}

      {task.artifacts.length > 0 && (
        <Card>
          <CardTitle>可下载的申请材料</CardTitle>
          <div className="grid gap-3 sm:grid-cols-2">
            {task.artifacts.map((artifact) => (
              <div key={artifact.kind} className="flex items-center justify-between gap-3 rounded-lg border border-black/[0.06] p-3">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium text-ink">{artifact.fileName}</p>
                  <p className="mt-0.5 truncate font-mono text-[10px] text-ink-tertiary">SHA-256 {artifact.sha256}</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={downloading === artifact.kind}
                  onClick={async () => {
                    setDownloading(artifact.kind)
                    try {
                      await downloadApplicationArtifact(artifact)
                      toast.success('申请材料已下载')
                    } catch (error) {
                      toast.error('下载失败', { description: actionError(error) })
                    } finally {
                      setDownloading(undefined)
                    }
                  }}
                >
                  <Download className="size-3.5" />下载
                </Button>
              </div>
            ))}
          </div>
          <div className="mt-4 flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[12px] leading-relaxed text-warning">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
            系统不会自动投递。请逐页检查事实、措辞、格式和联系方式，再到企业官网手动提交。
          </div>
        </Card>
      )}

      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="批准生成定制申请材料？"
        description="批准后将调用 DeepSeek 生成定制简历和求职信，并进行事实审查与招聘视角审查，可能产生 API 费用。"
        confirmLabel="批准并继续"
        onConfirm={() => mutate(approve, '已批准，开始生成和双重审查')}
      />
      <ConfirmDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        title="放弃本次申请？"
        description="本次任务会标记为已放弃，不会继续调用大模型或生成文件。"
        confirmLabel="确认放弃"
        destructive
        onConfirm={() => mutate(reject, '本次申请已放弃')}
      />
    </div>
  )
}
