import { useDeferredValue, useState } from 'react'
import {
  BookmarkPlus,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
  EyeOff,
  FileSearch,
  Loader2,
  MapPin,
  MessageCircleMore,
  Search,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/common/StateViews'
import { Pill } from '@/components/common/Badges'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { CompanyMonitorFields } from '@/components/companies/CompanyMonitorFields'
import { CandidateChannelDialog } from '@/components/candidates/CandidateChannelDialog'
import { CandidateWechatDialog } from '@/components/candidates/CandidateWechatDialog'
import {
  useCompanyCandidates,
  useDiscoverCompanyWebsite,
  useMonitorCompanyCandidate,
  useReviewCompanyCandidate,
} from '@/hooks/useCompanyCandidates'
import {
  COMPANY_TYPE_LABEL,
  INDUSTRY_CATEGORY_LABEL,
  RECRUITMENT_CHANNEL_STATUS_LABEL,
} from '@/types'
import type {
  CompanyCandidate,
  CompanyCandidateDecision,
  CompanyWebsiteDiscovery,
  RecruitmentChannel,
} from '@/types'
import { showMutationError } from '@/lib/mutationError'
import { useCompanyMonitorForm } from '@/hooks/useCompanyMonitorForm'

const FIT_LABEL = { high: '高适配初筛', medium: '中适配初筛', low: '待进一步判断' } as const
const DECISION_LABEL: Record<CompanyCandidateDecision, string> = {
  pending: '待背调',
  shortlisted: '已收藏',
  rejected: '暂不考虑',
  monitored: '已加入监控',
}
const SCALE_LABEL = {
  large: '大型集团',
  medium_or_above: '中型以上',
  medium: '中等规模',
  growth_stage: '成长型企业',
  unknown: '规模待核验',
} as const

function StatCard({ label, value, note, active = false, onClick }: { label: string; value: number; note: string; active?: boolean; onClick?: () => void }) {
  const card = (
    <Card className="space-y-1">
      <p className="text-[12px] text-ink-tertiary">{label}</p>
      <p className="text-2xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="text-[11px] text-ink-tertiary">{note}</p>
    </Card>
  )
  if (!onClick) return card
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-xl text-left transition hover:-translate-y-0.5 hover:shadow-sm ${active ? 'ring-2 ring-brand ring-offset-2' : ''}`}
    >
      {card}
    </button>
  )
}

function fitTone(level: CompanyCandidate['fitLevel']): 'green' | 'blue' | 'gray' {
  return level === 'high' ? 'green' : level === 'medium' ? 'blue' : 'gray'
}

function decisionTone(decision: CompanyCandidateDecision): 'green' | 'blue' | 'red' | 'gray' {
  if (decision === 'monitored') return 'green'
  if (decision === 'shortlisted') return 'blue'
  if (decision === 'rejected') return 'red'
  return 'gray'
}

function channelTone(candidate: CompanyCandidate): 'green' | 'blue' | 'amber' | 'gray' {
  if (candidate.recruitmentChannelStatus === 'official_careers') return 'green'
  if (candidate.recruitmentChannelStatus === 'group_recruitment'
    || candidate.recruitmentChannelStatus === 'official_notice_source') return 'blue'
  if (candidate.recruitmentChannelStatus === 'official_site_pending'
    || candidate.recruitmentChannelStatus === 'third_party_lead') return 'amber'
  return 'gray'
}

interface MonitorDialogProps {
  candidate: CompanyCandidate
  discovery?: CompanyWebsiteDiscovery | null
  onClose: () => void
}

function MonitorDialog({ candidate, discovery, onClose }: MonitorDialogProps) {
  const monitor = useMonitorCompanyCandidate()
  const form = useCompanyMonitorForm({
    website: candidate.officialWebsite ?? '',
    careersUrl: candidate.careersUrl ?? '',
    companyType: candidate.companyType,
    industryCategory: candidate.industryCategory,
    enabled: false,
  })

  const close = () => {
    onClose()
    form.reset()
  }

  const submit = () => {
    if (!form.value.website.trim()) {
      toast.error('请先填写核验过的企业官网')
      return
    }
    monitor.mutate(
      {
        id: candidate.id,
        input: {
          website: form.value.website.trim(),
          careersUrl: form.value.careersUrl.trim() || undefined,
          companyType: form.value.companyType,
          industryCategory: form.value.industryCategory,
          monitorMode: form.value.monitorMode,
          maxPages: Number(form.value.maxPages) || 20,
          enabled: form.value.enabled,
          recruitmentChannel: form.value.careersUrl.trim()
            ? 'official_careers'
            : 'official_homepage',
          note: form.value.note.trim() || undefined,
        },
      },
      {
        onSuccess: () => {
          toast.success(`「${candidate.name}」已加入企业监控`, {
            description: form.value.enabled ? '已启用，将参加下一次扫描。' : '默认暂停，请确认官网后再启用。',
          })
          close()
        },
        onError: (error) => showMutationError('加入监控失败', error),
      },
    )
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close()
      }}
    >
      <DialogContent className="max-h-[88vh] overflow-y-auto rounded-xl sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>把候选企业加入监控</DialogTitle>
          <DialogDescription>
            {candidate.name}。自动查找结果未达到直接加入标准，请核对网址；系统不会把搜索结果页或第三方招聘页冒充官网。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          {discovery && (
            <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-[12px] text-amber-950">
              <p className="font-medium">{discovery.message}</p>
              {discovery.candidates.length > 0 && (
                <div className="space-y-1.5">
                  {discovery.candidates.map((item) => (
                    <a key={item.website} href={item.website} target="_blank" rel="noreferrer" className="block truncate text-brand hover:underline">
                      {item.title || item.website}（可信分 {item.score}）
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}
          <CompanyMonitorFields
            value={form.value}
            onChange={form.update}
            idPrefix="candidate"
            enabledTitle="立即启用监控"
            enabledDescription="建议先保持关闭，测试官网连接后再启用"
            noteLabel="背调备注"
            notePlaceholder="例如：官网已核验；仍需确认双休、试用期制度和岗位边界"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={close}>取消</Button>
          <Button onClick={submit} disabled={monitor.isPending} className="bg-brand text-white hover:bg-brand-hover">
            {monitor.isPending && <Loader2 className="size-4 animate-spin" />}
            保存到监控列表
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function CompanyCandidatesPage() {
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [province, setProvince] = useState('__all__')
  const [fitLevel, setFitLevel] = useState('__all__')
  const [decision, setDecision] = useState('__all__')
  const [channelStatus, setChannelStatus] = useState('__all__')
  const [sourceKey, setSourceKey] = useState('__all__')
  const [techOnly, setTechOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [monitorTarget, setMonitorTarget] = useState<CompanyCandidate | null>(null)
  const [monitorDiscovery, setMonitorDiscovery] = useState<CompanyWebsiteDiscovery | null>(null)
  const [channelTarget, setChannelTarget] = useState<CompanyCandidate | null>(null)
  const [wechatTarget, setWechatTarget] = useState<CompanyCandidate | null>(null)
  const [autoMonitorId, setAutoMonitorId] = useState<string | null>(null)
  const review = useReviewCompanyCandidate()
  const discoverWebsite = useDiscoverCompanyWebsite()
  const quickMonitor = useMonitorCompanyCandidate()
  const candidates = useCompanyCandidates({
    q: deferredQuery,
    province: province === '__all__' ? undefined : province,
    fitLevel: fitLevel === '__all__' ? undefined : fitLevel as 'high' | 'medium' | 'low',
    decision: decision === '__all__' ? undefined : decision as CompanyCandidateDecision,
    channelStatus: channelStatus === '__all__'
      ? undefined
      : channelStatus as CompanyCandidate['recruitmentChannelStatus'],
    sourceKey: sourceKey === '__all__' ? undefined : sourceKey,
    techOnly,
    page,
    pageSize: 50,
  })
  const data = candidates.data

  const changeFilter = (setter: (value: string) => void, value: string) => {
    setter(value)
    setPage(1)
  }

  const setReview = (candidate: CompanyCandidate, next: 'pending' | 'shortlisted' | 'rejected') => {
    review.mutate(
      { id: candidate.id, input: { decision: next } },
      {
        onSuccess: () => toast.success(next === 'shortlisted' ? '已加入背调收藏' : next === 'rejected' ? '已标记为暂不考虑' : '已恢复为待背调'),
        onError: (error) => showMutationError('保存审批状态失败', error),
      },
    )
  }

  const openManualMonitor = (candidate: CompanyCandidate, discovery?: CompanyWebsiteDiscovery) => {
    setMonitorTarget({
      ...candidate,
      officialWebsite: discovery?.website ?? candidate.officialWebsite,
    })
    setMonitorDiscovery(discovery ?? null)
  }

  const monitorWithWebsite = (
    candidate: CompanyCandidate,
    website: string,
    reason: string,
    recruitmentChannel: RecruitmentChannel = 'official_homepage',
  ) => {
    quickMonitor.mutate(
      {
        id: candidate.id,
        input: {
          website,
          careersUrl: candidate.careersUrl,
          companyType: candidate.companyType,
          industryCategory: candidate.industryCategory,
          monitorMode: recruitmentChannel === 'official_notice_source' ? 'notices' : 'jobs',
          maxPages: 20,
          enabled: true,
          recruitmentChannel,
          parentCompany: recruitmentChannel === 'group_recruitment'
            ? candidate.parentCompany
            : undefined,
          attributionKeywords: recruitmentChannel === 'group_recruitment'
            ? candidate.attributionKeywords.length
              ? candidate.attributionKeywords
              : [candidate.name]
            : undefined,
          note: reason,
        },
      },
      {
        onSuccess: () => {
          toast.success(`「${candidate.name}」已自动加入并启用监控`, {
            description: '招聘入口留空时，扫描器会从官网首页继续发现。',
          })
          setAutoMonitorId(null)
        },
        onError: (error) => {
          showMutationError('自动加入监控失败，已打开人工确认', error)
          setAutoMonitorId(null)
          openManualMonitor({ ...candidate, officialWebsite: website })
        },
      },
    )
  }

  const addToMonitor = (candidate: CompanyCandidate) => {
    setAutoMonitorId(candidate.id)
    if (candidate.recruitmentChannelStatus === 'group_recruitment') {
      if (candidate.groupRecruitmentUrl) {
        monitorWithWebsite(
          candidate,
          candidate.groupRecruitmentUrl,
          `使用「${candidate.parentCompany}」集团招聘平台；仅接收正文明确命中本公司的岗位。`,
          'group_recruitment',
        )
        return
      }
      setAutoMonitorId(null)
      setChannelTarget(candidate)
      toast.info('请先补充集团招聘网址')
      return
    }
    if (candidate.recruitmentChannelStatus === 'official_notice_source') {
      const sourceUrl = candidate.careersUrl ?? candidate.officialWebsite
      if (sourceUrl) {
        monitorWithWebsite(
          candidate,
          sourceUrl,
          '使用已核验的官方公告来源。',
          'official_notice_source',
        )
        return
      }
      setAutoMonitorId(null)
      setChannelTarget(candidate)
      toast.info('请先登记官方公告来源')
      return
    }
    if ([
      'no_official_site',
      'no_careers_channel',
      'manual_only',
      'third_party_lead',
      'not_hiring',
    ].includes(candidate.recruitmentChannelStatus)) {
      setAutoMonitorId(null)
      setChannelTarget(candidate)
      toast.info('该企业当前不适合自动监控，请先维护招聘渠道')
      return
    }
    if (candidate.officialWebsite) {
      monitorWithWebsite(
        candidate,
        candidate.careersUrl ?? candidate.officialWebsite,
        '使用候选库中已保存并核验的官方入口。',
        candidate.careersUrl ? 'official_careers' : 'official_homepage',
      )
      return
    }
    discoverWebsite.mutate(candidate.id, {
      onSuccess: (result) => {
        if (result.status === 'found' && result.confidence === 'high' && result.website) {
          monitorWithWebsite(candidate, result.website, `官网自动发现：${result.message}`)
          return
        }
        setAutoMonitorId(null)
        openManualMonitor(candidate, result)
        toast.info('自动结果需要你确认一次', { description: result.message })
      },
      onError: (error) => {
        setAutoMonitorId(null)
        openManualMonitor(candidate)
        showMutationError('官网自动查找失败，已切换为手动填写', error)
      },
    })
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="优质企业候选库"
        subtitle="政府名单初筛、个人画像排序、人工背调后再加入每日监控"
      />

      {data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard label="官方名单候选" value={data.stats.total} note="不直接参与扫描" />
          <StatCard label="福建候选" value={data.stats.fujian} note="福州、厦门及省内企业" />
          <StatCard label="高适配初筛" value={data.stats.highFit} note="地区与技术名称信号" />
          <StatCard
            label="背调收藏"
            value={data.stats.shortlisted}
            note={decision === 'shortlisted' ? '点击返回全部候选' : '点击查看全部收藏'}
            active={decision === 'shortlisted'}
            onClick={() => {
              setDecision((value) => value === 'shortlisted' ? '__all__' : 'shortlisted')
              setTechOnly(false)
              setPage(1)
            }}
          />
          <StatCard label="已加入监控" value={data.stats.monitored} note="进入正式企业配置" />
        </div>
      )}

      <Card className="flex items-start gap-3 border-amber-200 bg-amber-50/70">
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-amber-700" />
        <div>
          <p className="text-[13px] font-semibold text-amber-950">“专精特新”是候选证据，不是员工体验背书</p>
          <p className="mt-0.5 text-[12px] leading-5 text-amber-900/80">
            {data?.disclaimer ?? '正在读取候选库说明…'} 系统不会声称这些企业一定双休、无仲裁或当前有校招岗位。
          </p>
        </div>
      </Card>

      <Card className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-[minmax(220px,1fr)_140px_140px_150px_160px_180px_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
            <Input
              value={query}
              onChange={(event) => { setQuery(event.target.value); setPage(1) }}
              placeholder="搜索企业、地区或技术方向"
              className="pl-9"
            />
          </div>
          <Select value={province} onValueChange={(value) => changeFilter(setProvince, value)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全国地区</SelectItem>
              {Object.entries(data?.provinceCounts ?? {}).map(([name, count]) => <SelectItem key={name} value={name}>{name}（{count}）</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={fitLevel} onValueChange={(value) => changeFilter(setFitLevel, value)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部适配度</SelectItem>
              <SelectItem value="high">高适配初筛</SelectItem>
              <SelectItem value="medium">中适配初筛</SelectItem>
              <SelectItem value="low">待进一步判断</SelectItem>
            </SelectContent>
          </Select>
          <Select value={decision} onValueChange={(value) => changeFilter(setDecision, value)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部审批状态</SelectItem>
              {(Object.keys(DECISION_LABEL) as CompanyCandidateDecision[]).map((value) => <SelectItem key={value} value={value}>{DECISION_LABEL[value]}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={channelStatus} onValueChange={(value) => changeFilter(setChannelStatus, value)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部招聘渠道</SelectItem>
              {(Object.keys(RECRUITMENT_CHANNEL_STATUS_LABEL) as CompanyCandidate['recruitmentChannelStatus'][]).map((value) => (
                <SelectItem key={value} value={value}>
                  {RECRUITMENT_CHANNEL_STATUS_LABEL[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={sourceKey} onValueChange={(value) => changeFilter(setSourceKey, value)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">全部优质来源</SelectItem>
              {(data?.sources ?? []).map((source) => (
                <SelectItem key={source.key} value={source.key}>{source.title}（{source.count}）</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center justify-between gap-3 rounded-lg bg-surface-subtle px-3">
            <span className="whitespace-nowrap text-[12px] text-ink-body">仅技术相关</span>
            <Switch checked={techOnly} onCheckedChange={(value) => { setTechOnly(value); setPage(1) }} />
          </div>
        </div>
        <p className="text-[12px] text-ink-tertiary">
          当前筛选 {data?.total ?? 0} 家；“适配分”只使用地区、目标岗位与企业名称中的技术信号，真实投递难度必须等抓到具体 JD 后评估。
        </p>
      </Card>

      {candidates.isLoading ? (
        <ListSkeleton rows={8} card />
      ) : candidates.isError ? (
        <Card padded={false}><ErrorState onRetry={() => candidates.refetch()} /></Card>
      ) : !data || data.items.length === 0 ? (
        <Card padded={false}>
          <EmptyState icon={<Database className="size-6" />} title="没有符合条件的候选企业" description="可以放宽地区、适配度或技术方向筛选。" />
        </Card>
      ) : (
        <div className="space-y-3">
          {data.items.map((candidate) => (
            <Card key={candidate.id} className="space-y-3">
              <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-start">
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-[16px] font-semibold text-ink">{candidate.name}</h2>
                    <Pill tone={fitTone(candidate.fitLevel)}>{FIT_LABEL[candidate.fitLevel]} · {candidate.fitScore}</Pill>
                    <Pill tone={decisionTone(candidate.decision)}>{DECISION_LABEL[candidate.decision]}</Pill>
                    {candidate.province === '福建' && <Pill tone="green">福建优先</Pill>}
                    <Pill tone="gray">{COMPANY_TYPE_LABEL[candidate.companyType]}</Pill>
                    <Pill tone="gray">{SCALE_LABEL[candidate.scaleLevel ?? 'unknown']}</Pill>
                    <Pill tone={channelTone(candidate)}>
                      {RECRUITMENT_CHANNEL_STATUS_LABEL[candidate.recruitmentChannelStatus]}
                    </Pill>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-ink-tertiary">
                    <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{candidate.city ?? candidate.province}</span>
                    <span>{INDUSTRY_CATEGORY_LABEL[candidate.industryCategory]}（名称初筛）</span>
                    <span>官方证据分 {candidate.qualityEvidenceScore}/100</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {candidate.techSignals.length ? candidate.techSignals.map((signal) => <Pill key={signal} tone="blue">{signal}</Pill>) : <Pill tone="gray">名称未呈现技术方向</Pill>}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => setWechatTarget(candidate)}>
                    <MessageCircleMore className="size-3.5" />
                    公众号招聘
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setChannelTarget(candidate)}>
                    <FileSearch className="size-3.5" />
                    招聘渠道与来源
                  </Button>
                  {candidate.decision !== 'monitored' && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => setReview(candidate, candidate.decision === 'shortlisted' ? 'pending' : 'shortlisted')}>
                        {candidate.decision === 'shortlisted' ? <CheckCircle2 className="size-3.5" /> : <BookmarkPlus className="size-3.5" />}
                        {candidate.decision === 'shortlisted' ? '取消收藏' : '背调收藏'}
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setReview(candidate, candidate.decision === 'rejected' ? 'pending' : 'rejected')}>
                        <EyeOff className="size-3.5" />
                        {candidate.decision === 'rejected' ? '恢复考虑' : '暂不考虑'}
                      </Button>
                      <Button
                        size="sm"
                        className="bg-brand text-white hover:bg-brand-hover"
                        disabled={autoMonitorId !== null}
                        onClick={() => addToMonitor(candidate)}
                      >
                        {autoMonitorId === candidate.id ? <Loader2 className="size-3.5 animate-spin" /> : <Building2 className="size-3.5" />}
                        {autoMonitorId === candidate.id ? '查找官网并加入…' : '一键加入监控'}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className="grid gap-3 border-t border-black/[0.05] pt-3 md:grid-cols-[1fr_auto] md:items-center">
                <div>
                  <p className="text-[12px] text-ink-body">{candidate.fitReasons.join('；')}</p>
                  {candidate.scaleEvidence?.length ? (
                    <p className="mt-1 text-[11px] text-ink-tertiary">规模证据：{candidate.scaleEvidence.join('；')}</p>
                  ) : null}
                  <p className="mt-1 text-[11px] text-ink-tertiary">待核验：成立年限、经营与现金流、劳动争议、单双休、试用期制度、岗位边界、招聘真实性。</p>
                </div>
                <a href={candidate.evidenceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] font-medium text-brand hover:underline">
                  查看工信部 PDF 证据 <ExternalLink className="size-3.5" />
                </a>
              </div>
            </Card>
          ))}

          <Card className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[12px] text-ink-tertiary">第 {data.page} / {data.pages} 页，每页 {data.pageSize} 家</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1 || candidates.isFetching} onClick={() => setPage((value) => Math.max(1, value - 1))}>
                <ChevronLeft className="size-4" />上一页
              </Button>
              <Button variant="outline" size="sm" disabled={page >= data.pages || candidates.isFetching} onClick={() => setPage((value) => value + 1)}>
                下一页<ChevronRight className="size-4" />
              </Button>
            </div>
          </Card>
        </div>
      )}

      <Card className="flex items-start gap-3">
        <Sparkles className="mt-0.5 size-4 text-brand" />
        <div className="text-[12px] leading-5 text-ink-secondary">
          <p className="font-medium text-ink">建议审批顺序</p>
          <p>先筛“福建 + 技术相关 + 高适配”，收藏后人工核验官网和近期招聘，再加入监控。不要因为公司进入政府名单就跳过劳动制度与岗位边界核查。</p>
        </div>
      </Card>

      {monitorTarget && (
        <MonitorDialog
          key={monitorTarget.id}
          candidate={monitorTarget}
          discovery={monitorDiscovery}
          onClose={() => {
            setMonitorTarget(null)
            setMonitorDiscovery(null)
          }}
        />
      )}
      {channelTarget && (
        <CandidateChannelDialog
          key={channelTarget.id}
          candidate={channelTarget}
          onClose={() => setChannelTarget(null)}
        />
      )}
      {wechatTarget && (
        <CandidateWechatDialog
          key={wechatTarget.id}
          candidate={wechatTarget}
          onClose={() => setWechatTarget(null)}
        />
      )}
    </div>
  )
}
