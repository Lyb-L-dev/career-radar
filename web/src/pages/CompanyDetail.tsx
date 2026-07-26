import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  ArrowLeft,
  Play,
  Pencil,
  Pause,
  ExternalLink,
  ChevronDown,
  CheckCircle2,
  XCircle,
  CircleHelp,
  Globe,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { CompanyStatusBadge, Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState, EmptyState } from '@/components/common/StateViews'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useCompany, useCompanyPageRecords, useCompanyErrors, useUpdateCompany } from '@/hooks/useCompanies'
import { useRuns } from '@/hooks/useData'
import { useJobs } from '@/hooks/useJobs'
import { COMPANY_TYPE_LABEL, MONITOR_MODE_LABEL, RENDER_MODE_LABEL } from '@/types'
import { createRun } from '@/services/runs'
import type { Company, CompanyType } from '@/types'
import { cn } from '@/lib/utils'

function EditCompanyDialog({
  company,
  open,
  onOpenChange,
  onSave,
}: {
  company: Company
  open: boolean
  onOpenChange: (value: boolean) => void
  onSave: (patch: Partial<Company>) => Promise<unknown>
}) {
  const [name, setName] = useState(company.name)
  const [website, setWebsite] = useState(company.website)
  const [companyType, setCompanyType] = useState<CompanyType>(company.companyType)
  const [maxPages, setMaxPages] = useState(String(company.maxPages))
  const [note, setNote] = useState(company.note ?? '')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!name.trim() || !website.trim()) {
      toast.error('企业名称与官网地址不能为空')
      return
    }
    if (!Number.isInteger(Number(maxPages)) || Number(maxPages) < 1) {
      toast.error('最大扫描页面数必须是大于 0 的整数')
      return
    }
    setSaving(true)
    try {
      await onSave({
        name: name.trim(),
        website: website.trim(),
        careersUrl: website.trim(),
        companyType,
        maxPages: Number(maxPages),
        note: note.trim() || undefined,
      })
      toast.success('企业配置已写入 config.yaml')
      onOpenChange(false)
    } catch (error) {
      toast.error('保存企业配置失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>编辑企业配置</DialogTitle>
          <DialogDescription>保存前会校验 URL 与完整 YAML，并自动保留一份 config.yaml.bak。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="edit-company-name">企业名称</Label>
            <Input id="edit-company-name" value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-company-url">官网或招聘页 URL</Label>
            <Input id="edit-company-url" value={website} onChange={(event) => setWebsite(event.target.value)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>公司类型</Label>
              <Select value={companyType} onValueChange={(value) => setCompanyType(value as CompanyType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(COMPANY_TYPE_LABEL) as CompanyType[]).map((type) => (
                    <SelectItem key={type} value={type}>{COMPANY_TYPE_LABEL[type]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="edit-company-max-pages">最大扫描页面数</Label>
              <Input id="edit-company-max-pages" type="number" min={1} max={5000} value={maxPages} onChange={(event) => setMaxPages(event.target.value)} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="edit-company-note">备注</Label>
            <Textarea id="edit-company-note" value={note} onChange={(event) => setNote(event.target.value)} rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button className="bg-brand hover:bg-brand-hover text-white" onClick={save} disabled={saving}>
            {saving ? '保存中…' : '保存配置'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { data: company, isLoading, isError, refetch } = useCompany(id ?? '')
  const { data: pageRecords } = useCompanyPageRecords(
    id ?? '',
    company?.status === 'scanning',
  )
  const { data: errors } = useCompanyErrors(id ?? '')
  const { data: companyJobs } = useJobs({ tab: 'all', companyId: id })
  const { data: runs } = useRuns()
  const updateCompany = useUpdateCompany()
  const [pauseOpen, setPauseOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(searchParams.get('edit') === '1')
  const [starting, setStarting] = useState(false)

  if (isLoading) return <PageSkeleton />
  if (isError) return <ErrorState onRetry={() => refetch()} />
  if (!company)
    return (
      <EmptyState
        title="没有找到这家企业"
        description="企业可能已被删除。"
        actions={<Button variant="outline" onClick={() => navigate('/companies')}>返回企业监控</Button>}
      />
    )

  const relatedRuns = (runs ?? []).filter((r) => r.companies.some((c) => c.companyId === company.id))
  const startScan = async () => {
    setStarting(true)
    try {
      const result = await createRun({ scope: 'company', companyId: company.id, sendEmail: false })
      toast.success(`已创建「${company.name}」真实扫描任务`)
      navigate(`/runs/${result.runId}`)
    } catch (error) {
      toast.error('创建扫描任务失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="space-y-5">
      <Link to="/companies" className="inline-flex items-center gap-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors">
        <ArrowLeft className="size-4" />
        返回企业监控
      </Link>

      {/* 企业信息区 */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[24px] font-semibold text-ink">{company.name}</h1>
              <Pill tone={company.companyType === 'central_soe' || company.companyType === 'local_soe' ? 'blue' : 'gray'}>
                {COMPANY_TYPE_LABEL[company.companyType]}
              </Pill>
              <CompanyStatusBadge status={company.status} />
            </div>
            <a
              href={company.website}
              target="_blank"
              rel="noreferrer"
              className="mt-1.5 inline-flex items-center gap-1 text-[14px] text-brand hover:underline"
            >
              <Globe className="size-3.5" />
              {company.website}
            </a>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-secondary">
              <span>行业：{company.industry}</span>
              <span>地区：{[company.province, company.city].filter(Boolean).join(' ') || '未设置'}</span>
              <span>监控：{MONITOR_MODE_LABEL[company.monitorMode ?? 'jobs']}</span>
              <span>渲染模式：{RENDER_MODE_LABEL[company.renderMode]}</span>
              <span>单家最大页面数：{company.maxPages}</span>
              <span>添加时间：{company.addedAt}</span>
            </div>
            {company.note && <p className="mt-2 text-[13px] text-ink-tertiary">备注：{company.note}</p>}
            {!!company.governmentHonors?.length && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {company.governmentHonors.map((honor) => <Pill key={honor} tone="green">政府公示：{honor}</Pill>)}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button className="bg-brand hover:bg-brand-hover text-white" onClick={startScan} disabled={starting || !company.enabled}>
              <Play className="size-4" />
              {starting ? '创建中…' : '立即扫描'}
            </Button>
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="size-4" />
              编辑配置
            </Button>
            <Button variant="outline" onClick={() => setPauseOpen(true)}>
              <Pause className="size-4" />
              {company.status === 'paused' ? '恢复监控' : '暂停监控'}
            </Button>
          </div>
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        {/* 监控概览 */}
        <Card>
          <CardTitle>监控概览</CardTitle>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              { label: '最近发现岗位', value: `${company.recentJobCount} 个` },
              { label: '最后扫描', value: company.lastScanAt ?? '从未' },
              { label: '连续失败', value: `${company.consecutiveFailures} 次` },
              { label: '启用状态', value: company.enabled ? '已启用' : '已停用' },
            ].map((s) => (
              <div key={s.label} className="rounded-lg bg-surface-subtle p-3.5">
                <p className="text-[18px] font-semibold text-ink">{s.value}</p>
                <p className="mt-0.5 text-[12px] text-ink-tertiary">{s.label}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-2.5 text-[13px]">
            <div className="flex items-center justify-between rounded-lg border border-black/[0.06] px-3.5 py-2.5">
              <span className="text-ink-secondary">招聘入口识别结果</span>
              {company.discoveredEntry ? (
                <a href={company.discoveredEntry} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-brand hover:underline truncate max-w-[240px]">
                  {company.discoveredEntry}
                  <ExternalLink className="size-3 shrink-0" />
                </a>
              ) : (
                <span className="text-ink-tertiary">尚未识别，首次验证时自动发现</span>
              )}
            </div>
            <div className="flex items-center justify-between rounded-lg border border-black/[0.06] px-3.5 py-2.5">
              <span className="text-ink-secondary">robots.txt 检查</span>
              {company.robotsStatus === 'allowed' ? (
                <span className="flex items-center gap-1.5 text-success"><CheckCircle2 className="size-4" />允许抓取招聘路径</span>
              ) : company.robotsStatus === 'blocked' ? (
                <span className="flex items-center gap-1.5 text-danger"><XCircle className="size-4" />招聘路径被禁止，已停止访问</span>
              ) : (
                <span className="flex items-center gap-1.5 text-ink-tertiary"><CircleHelp className="size-4" />尚未检查</span>
              )}
            </div>
          </div>
        </Card>

        {/* 最近发现岗位 */}
        <Card>
          <CardTitle
            extra={
              <Link to={`/jobs?tab=all&company=${company.id}`} className="text-[13px] text-brand hover:underline">
                在岗位中心查看
              </Link>
            }
          >
            最近发现岗位
          </CardTitle>
          {!companyJobs || companyJobs.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-ink-tertiary">暂未从该企业发现岗位，完成首次扫描后这里会展示结果。</p>
          ) : (
            <ul className="divide-y divide-black/[0.05]">
              {companyJobs.slice(0, 5).map((j) => (
                <li key={j.id}>
                  <Link to={`/jobs/${j.id}`} className="flex items-center justify-between gap-3 py-2.5 group">
                    <div className="min-w-0">
                      <p className="truncate text-[14px] text-ink group-hover:text-brand transition-colors">{j.title}</p>
                      <p className="text-[12px] text-ink-tertiary">{j.city} · 更新于 {j.lastUpdatedAt.slice(5, 16)}</p>
                    </div>
                    <Pill tone={j.status === 'new' ? 'green' : j.status === 'updated' ? 'blue' : 'gray'}>
                      {j.status === 'new' ? '新增' : j.status === 'updated' ? '更新' : j.status === 'closed' ? '已关闭' : '已忽略'}
                    </Pill>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* 扫描页面记录 */}
      <Card>
        <CardTitle>扫描页面记录</CardTitle>
        {!pageRecords || pageRecords.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-ink-tertiary">暂无页面抓取记录。</p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>页面 URL</TableHead>
                  <TableHead>页面类型</TableHead>
                  <TableHead>抓取方式</TableHead>
                  <TableHead>HTTP 状态</TableHead>
                  <TableHead>正文长度</TableHead>
                  <TableHead>进入 LLM</TableHead>
                  <TableHead>抓取时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageRecords.map((p) => (
                  <TableRow key={p.url + p.fetchedAt}>
                    <TableCell className="max-w-[320px] truncate font-mono text-[12px]" title={p.url}>{p.url}</TableCell>
                    <TableCell className="text-[13px]">{p.pageType}</TableCell>
                    <TableCell className="text-[13px]">{p.method === 'requests' ? 'requests 静态' : 'Playwright 渲染'}</TableCell>
                    <TableCell>
                      <Pill tone={p.httpStatus === 200 ? 'green' : 'red'}>{p.httpStatus ?? '失败'}</Pill>
                    </TableCell>
                    <TableCell className="tabular-nums text-[13px]">{(p.contentLength / 1000).toFixed(1)}k 字符</TableCell>
                    <TableCell className="text-[13px]">{p.llmExtracted ? '是' : '否'}</TableCell>
                    <TableCell className="text-[12px] text-ink-tertiary tabular-nums">{p.fetchedAt}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {/* 最近错误 + 运行历史 */}
      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardTitle>最近错误</CardTitle>
          {!errors || errors.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-ink-tertiary">近期没有错误记录，运行状况良好。</p>
          ) : (
            <ul className="space-y-3">
              {errors.map((e) => (
                <li key={e.time} className="rounded-lg bg-surface-subtle p-4">
                  <div className="flex items-start gap-2.5">
                    <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] text-ink-body">{e.message}</p>
                      <p className="mt-1 text-[12px] text-ink-tertiary">{e.time}</p>
                      <Collapsible>
                        <CollapsibleTrigger className="mt-2 flex items-center gap-1 text-[12px] text-brand hover:underline">
                          查看技术详情
                          <ChevronDown className="size-3.5" />
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                          <pre className="mt-2 overflow-auto rounded-lg bg-ink p-3 text-[11px] leading-relaxed text-white/80 scrollbar-thin">
                            {e.technicalDetail}
                          </pre>
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardTitle>企业运行历史</CardTitle>
          {relatedRuns.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-ink-tertiary">暂无运行记录。</p>
          ) : (
            <ul className="divide-y divide-black/[0.05]">
              {relatedRuns.map((r) => {
                const cr = r.companies.find((c) => c.companyId === company.id)!
                return (
                  <li key={r.id}>
                    <Link to={`/runs/${r.id}`} className="flex items-center justify-between gap-3 py-2.5 group">
                      <div>
                        <p className="text-[13px] font-medium text-ink group-hover:text-brand transition-colors">{r.code}</p>
                        <p className="text-[12px] text-ink-tertiary">{r.startedAt}</p>
                      </div>
                      <span
                        className={cn(
                          'text-[12px]',
                          cr.status === 'success' ? 'text-success' : cr.status === 'failed' ? 'text-danger' : 'text-ink-tertiary',
                        )}
                      >
                        {cr.status === 'success' ? `成功 · +${cr.newJobs}/↑${cr.updatedJobs}` : cr.status === 'failed' ? '失败' : cr.status === 'skipped' ? '跳过' : '等待'}
                      </span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={pauseOpen}
        onOpenChange={setPauseOpen}
        title={company.status === 'paused' ? `恢复监控「${company.name}」？` : `暂停监控「${company.name}」？`}
        description={
          company.status === 'paused'
            ? '恢复后该企业将重新参与每日自动扫描。'
            : '暂停期间该企业不参与每日扫描，已抓取的岗位保留。可随时恢复。'
        }
        confirmLabel={company.status === 'paused' ? '恢复监控' : '暂停监控'}
        onConfirm={() => {
          const paused = company.status === 'paused'
          updateCompany.mutate({ id: company.id, patch: { status: paused ? 'active' : 'paused', enabled: paused } })
          toast.success(paused ? '已恢复监控' : '已暂停监控')
          setPauseOpen(false)
        }}
      />
      <EditCompanyDialog
        key={`${company.id}-${company.name}-${company.website}-${company.companyType}-${company.maxPages}-${company.note ?? ''}`}
        company={company}
        open={editOpen}
        onOpenChange={setEditOpen}
        onSave={(patch) => updateCompany.mutateAsync({ id: company.id, patch })}
      />
    </div>
  )
}
