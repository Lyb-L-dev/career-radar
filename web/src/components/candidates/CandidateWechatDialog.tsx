import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ExternalLink,
  Loader2,
  MessageCircleMore,
  Pencil,
  Play,
  Plus,
  ShieldCheck,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { Pill } from '@/components/common/Badges'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  useDeleteWechatAccount,
  useLatestWechatScan,
  useSaveWechatAccount,
  useStartWechatScan,
  useWechatAccounts,
  useWechatArticles,
  useWechatHealth,
} from '@/hooks/useWechatRecruitment'
import { showMutationError } from '@/lib/mutationError'
import type {
  CompanyCandidate,
  WechatAccountScope,
  WechatAccountVerification,
  WechatArticleClassification,
  WechatRecruitmentAccount,
  WechatRecruitmentScanStatus,
} from '@/types'

const VERIFICATION_LABEL: Record<WechatAccountVerification, string> = {
  verified: '已人工核验',
  pending: '待核验',
  rejected: '已排除',
}

const SCAN_STATUS_LABEL: Record<WechatRecruitmentScanStatus, string> = {
  pending: '等待开始',
  running: '正在扫描',
  completed: '扫描完成',
  partial: '部分完成',
  failed: '扫描失败',
  interrupted: '扫描中断',
}

const CLASSIFICATION: Record<
  WechatArticleClassification,
  { label: string; tone: 'green' | 'amber' | 'gray' }
> = {
  official_recruitment: { label: '官方招聘', tone: 'green' },
  third_party_lead: { label: '待核验线索', tone: 'amber' },
  non_recruitment: { label: '非招聘正文', tone: 'gray' },
}

interface Props {
  candidate: CompanyCandidate
  onClose: () => void
}

interface AccountForm {
  id?: string
  accountName: string
  accountIdentifier: string
  bizId: string
  scope: WechatAccountScope
  parentCompany: string
  attributionKeywords: string
  verificationStatus: WechatAccountVerification
  enabled: boolean
}

function emptyForm(candidate: CompanyCandidate): AccountForm {
  return {
    accountName: '',
    accountIdentifier: '',
    bizId: '',
    scope: 'company',
    parentCompany: candidate.parentCompany ?? '',
    attributionKeywords: candidate.name,
    verificationStatus: 'pending',
    enabled: true,
  }
}

function accountForm(account: WechatRecruitmentAccount): AccountForm {
  return {
    id: account.id,
    accountName: account.accountName,
    accountIdentifier: account.accountIdentifier ?? '',
    bizId: account.bizId ?? '',
    scope: account.scope,
    parentCompany: account.parentCompany ?? '',
    attributionKeywords: account.attributionKeywords.join('、'),
    verificationStatus: account.verificationStatus,
    enabled: account.enabled,
  }
}

function splitKeywords(value: string): string[] {
  return [...new Set(
    value
      .split(/[、，,\n]/)
      .map((item) => item.trim())
      .filter(Boolean),
  )]
}

function terminalStatus(status?: WechatRecruitmentScanStatus): boolean {
  return Boolean(status && !['pending', 'running'].includes(status))
}

export function CandidateWechatDialog({ candidate, onClose }: Props) {
  const queryClient = useQueryClient()
  const health = useWechatHealth()
  const accounts = useWechatAccounts(candidate.id)
  const articles = useWechatArticles(candidate.id)
  const latestScan = useLatestWechatScan(candidate.id)
  const saveAccount = useSaveWechatAccount()
  const deleteAccount = useDeleteWechatAccount()
  const startScan = useStartWechatScan()
  const [form, setForm] = useState<AccountForm>(() => emptyForm(candidate))
  const [showForm, setShowForm] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<WechatRecruitmentAccount | null>(null)

  const scanRunning = latestScan.data?.status === 'pending'
    || latestScan.data?.status === 'running'
  const enabledAccounts = useMemo(
    () => accounts.data?.filter((item) => item.enabled) ?? [],
    [accounts.data],
  )

  useEffect(() => {
    if (!terminalStatus(latestScan.data?.status)) return
    void queryClient.invalidateQueries({
      queryKey: ['wechat-recruitment', candidate.id, 'articles'],
    })
    void queryClient.invalidateQueries({
      queryKey: ['company-candidates', candidate.id, 'sources'],
    })
    void queryClient.invalidateQueries({ queryKey: ['jobs'] })
  }, [
    candidate.id,
    latestScan.data?.status,
    latestScan.data?.updatedAt,
    queryClient,
  ])

  const resetForm = () => {
    setForm(emptyForm(candidate))
    setShowForm(false)
  }

  const submitAccount = () => {
    const keywords = splitKeywords(form.attributionKeywords)
    if (!form.accountName.trim()) {
      toast.error('请填写公众号名称')
      return
    }
    if (form.scope === 'group' && (!form.parentCompany.trim() || keywords.length === 0)) {
      toast.error('集团公众号需要填写母集团和目标子公司归属关键词')
      return
    }
    saveAccount.mutate(
      {
        candidateId: candidate.id,
        accountId: form.id,
        input: {
          accountName: form.accountName.trim(),
          accountIdentifier: form.accountIdentifier.trim() || undefined,
          bizId: form.bizId.trim() || undefined,
          scope: form.scope,
          parentCompany: form.scope === 'group'
            ? form.parentCompany.trim()
            : undefined,
          attributionKeywords: form.scope === 'group'
            ? keywords
            : keywords.length ? keywords : [candidate.name],
          verificationStatus: form.verificationStatus,
          enabled: form.enabled,
        },
      },
      {
        onSuccess: () => {
          toast.success(form.id ? '公众号绑定已更新' : '公众号已登记')
          resetForm()
        },
        onError: (error) => showMutationError('保存公众号失败', error),
      },
    )
  }

  const runScan = () => {
    startScan.mutate(candidate.id, {
      onSuccess: () => toast.success('公众号招聘扫描已开始', {
        description: '仅运行本地规则，不会调用 DeepSeek。',
      }),
      onError: (error) => showMutationError('启动公众号扫描失败', error),
    })
  }

  const confirmDelete = () => {
    if (!deleteTarget) return
    deleteAccount.mutate(
      { candidateId: candidate.id, accountId: deleteTarget.id },
      {
        onSuccess: () => {
          toast.success('公众号绑定已删除，历史文章仍保留')
          setDeleteTarget(null)
        },
        onError: (error) => showMutationError('删除公众号绑定失败', error),
      },
    )
  }

  return (
    <>
      <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto rounded-xl sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>微信公众号招聘</DialogTitle>
            <DialogDescription>
              {candidate.name}。登记并人工核验企业招聘公众号后，可搜索和读取公开文章；
              未命中已核验身份的内容只会保存为待核验线索。
            </DialogDescription>
          </DialogHeader>

          <section className="space-y-3 rounded-xl border border-black/[0.07] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <MessageCircleMore className="mt-0.5 size-4 text-brand" />
                <div>
                  <h3 className="text-[13px] font-semibold text-ink">公众号绑定</h3>
                  <p className="text-[11px] leading-5 text-ink-tertiary">
                    “已人工核验”只能在确认公众号主页名称、微信号或文章账号身份后选择。
                    只填名称也能工作，但填写微信号或文章链接中的 __biz 可降低同名误判。
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setForm(emptyForm(candidate))
                  setShowForm(true)
                }}
              >
                <Plus className="size-3.5" />
                登记公众号
              </Button>
            </div>

            {accounts.isLoading ? (
              <p className="text-[12px] text-ink-tertiary">正在读取公众号绑定…</p>
            ) : !accounts.data?.length ? (
              <p className="rounded-lg bg-surface-subtle p-3 text-[12px] text-ink-tertiary">
                尚未登记公众号。企业没有独立招聘官网时，可以从企业招聘公众号开始。
              </p>
            ) : (
              <div className="space-y-2">
                {accounts.data.map((account) => (
                  <div
                    key={account.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-black/[0.06] p-3"
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[12px] font-medium text-ink">
                          {account.accountName}
                        </span>
                        <Pill tone={
                          account.verificationStatus === 'verified'
                            ? 'green'
                            : account.verificationStatus === 'rejected' ? 'gray' : 'amber'
                        }
                        >
                          {VERIFICATION_LABEL[account.verificationStatus]}
                        </Pill>
                        <Pill tone="gray">{account.scope === 'group' ? '集团公众号' : '企业公众号'}</Pill>
                        {!account.enabled && <Pill tone="gray">已暂停</Pill>}
                      </div>
                      <p className="text-[11px] text-ink-tertiary">
                        {account.accountIdentifier
                          ? `微信号：${account.accountIdentifier}`
                          : account.bizId ? `__biz：${account.bizId}` : '未填写微信号或 __biz'}
                        {account.scope === 'group' && account.attributionKeywords.length
                          ? ` · 归属词：${account.attributionKeywords.join('、')}`
                          : ''}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`编辑 ${account.accountName}`}
                        onClick={() => {
                          setForm(accountForm(account))
                          setShowForm(true)
                        }}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`删除 ${account.accountName}`}
                        onClick={() => setDeleteTarget(account)}
                      >
                        <Trash2 className="size-3.5 text-danger" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {showForm && (
              <div className="space-y-3 rounded-lg bg-surface-subtle p-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <Input
                    value={form.accountName}
                    onChange={(event) => setForm({ ...form, accountName: event.target.value })}
                    placeholder="公众号名称（必填）"
                  />
                  <Input
                    value={form.accountIdentifier}
                    onChange={(event) => setForm({
                      ...form,
                      accountIdentifier: event.target.value,
                    })}
                    placeholder="微信号（推荐填写）"
                  />
                  <Input
                    value={form.bizId}
                    onChange={(event) => setForm({ ...form, bizId: event.target.value })}
                    placeholder="文章链接中的 __biz（可选）"
                  />
                  <Select
                    value={form.scope}
                    onValueChange={(value) => setForm({
                      ...form,
                      scope: value as WechatAccountScope,
                    })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="company">本企业公众号</SelectItem>
                      <SelectItem value="group">集团统一招聘公众号</SelectItem>
                    </SelectContent>
                  </Select>
                  {form.scope === 'group' && (
                    <>
                      <Input
                        value={form.parentCompany}
                        onChange={(event) => setForm({
                          ...form,
                          parentCompany: event.target.value,
                        })}
                        placeholder="母集团名称（必填）"
                      />
                      <Input
                        value={form.attributionKeywords}
                        onChange={(event) => setForm({
                          ...form,
                          attributionKeywords: event.target.value,
                        })}
                        placeholder="目标子公司归属词，用顿号或逗号分隔"
                      />
                    </>
                  )}
                  <Select
                    value={form.verificationStatus}
                    onValueChange={(value) => setForm({
                      ...form,
                      verificationStatus: value as WechatAccountVerification,
                    })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="pending">待人工核验</SelectItem>
                      <SelectItem value="verified">已人工核验</SelectItem>
                      <SelectItem value="rejected">已排除</SelectItem>
                    </SelectContent>
                  </Select>
                  <label className="flex items-center justify-between rounded-md border border-black/[0.08] bg-white px-3 text-[12px] text-ink-body">
                    参与公众号扫描
                    <Switch
                      checked={form.enabled}
                      onCheckedChange={(enabled) => setForm({ ...form, enabled })}
                    />
                  </label>
                </div>
                {form.verificationStatus === 'verified' && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-[11px] leading-5 text-amber-950">
                    <ShieldCheck className="mt-0.5 size-4 shrink-0" />
                    请确认这确实是企业或母集团官方账号。核验错误可能把文章导入为官方招聘通知。
                  </div>
                )}
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="outline" onClick={resetForm}>取消</Button>
                  <Button size="sm" onClick={submitAccount} disabled={saveAccount.isPending}>
                    {saveAccount.isPending && <Loader2 className="size-3.5 animate-spin" />}
                    保存公众号
                  </Button>
                </div>
              </div>
            )}
          </section>

          <section className="space-y-3 rounded-xl border border-black/[0.07] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-[13px] font-semibold text-ink">公开文章扫描</h3>
                <p className="mt-0.5 text-[11px] leading-5 text-ink-tertiary">
                  通过本机 OpenCLI 搜索和读取公开文章，使用本地规则分类，不登录微信，也不调用 DeepSeek。
                </p>
                <p className={`mt-1 text-[11px] ${
                  health.data?.available ? 'text-success' : 'text-warning'
                }`}
                >
                  {health.isLoading
                    ? '正在检查本机能力…'
                    : health.data?.message ?? '无法读取公众号搜索状态'}
                </p>
              </div>
              <Button
                size="sm"
                onClick={runScan}
                disabled={
                  health.isLoading
                  || !health.data?.available
                  || enabledAccounts.length === 0
                  || scanRunning
                  || startScan.isPending
                }
              >
                {scanRunning || startScan.isPending
                  ? <Loader2 className="size-3.5 animate-spin" />
                  : <Play className="size-3.5" />}
                {scanRunning ? '扫描中' : '开始扫描'}
              </Button>
            </div>

            {latestScan.data && (
              <div className="space-y-2 rounded-lg bg-surface-subtle p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={
                    latestScan.data.status === 'completed'
                      ? 'green'
                      : latestScan.data.status === 'failed' ? 'red' : 'amber'
                  }
                  >
                    {SCAN_STATUS_LABEL[latestScan.data.status]}
                  </Pill>
                  <span className="text-[11px] text-ink-tertiary">
                    读取 {latestScan.data.stats.read} 篇 · 官方 {latestScan.data.stats.official} 篇
                    · 线索 {latestScan.data.stats.leads} 篇 · 忽略 {latestScan.data.stats.ignored} 篇
                  </span>
                </div>
                {latestScan.data.errors.length > 0 && (
                  <p className="line-clamp-3 whitespace-pre-wrap text-[11px] leading-5 text-danger">
                    {latestScan.data.errors.join('\n')}
                  </p>
                )}
              </div>
            )}

            {articles.isLoading ? (
              <p className="text-[12px] text-ink-tertiary">正在读取历史文章…</p>
            ) : !articles.data?.length ? (
              <p className="rounded-lg bg-surface-subtle p-3 text-[12px] text-ink-tertiary">
                尚无公众号文章记录。
              </p>
            ) : (
              <div className="space-y-2">
                {articles.data.map((article) => {
                  const classification = CLASSIFICATION[article.classification]
                  return (
                    <div key={article.id} className="space-y-1 rounded-lg border border-black/[0.06] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noreferrer"
                          className="min-w-0 truncate text-[12px] font-medium text-brand hover:underline"
                        >
                          {article.title} <ExternalLink className="inline size-3" />
                        </a>
                        <Pill tone={classification.tone}>{classification.label}</Pill>
                        {article.importedJobId && <Pill tone="blue">已导入通知</Pill>}
                      </div>
                      <p className="text-[11px] text-ink-tertiary">
                        {article.accountName || '未识别公众号'}
                        {article.publishedAt ? ` · ${article.publishedAt}` : ''}
                      </p>
                      <p className="line-clamp-2 text-[11px] leading-5 text-ink-secondary">
                        {article.reason}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null) }}
        title="删除公众号绑定？"
        description={`将停止扫描“${deleteTarget?.accountName ?? ''}”，已保存的历史文章和招聘通知不会删除。`}
        confirmLabel="删除绑定"
        destructive
        confirmDisabled={deleteAccount.isPending}
        onConfirm={confirmDelete}
      />
    </>
  )
}
