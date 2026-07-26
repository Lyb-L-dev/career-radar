import { useState } from 'react'
import { ExternalLink, FilePlus2, Loader2, ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'
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
import { Textarea } from '@/components/ui/textarea'
import {
  useAddCandidateSource,
  useCandidateSources,
  useReviewCompanyCandidate,
} from '@/hooks/useCompanyCandidates'
import { showMutationError } from '@/lib/mutationError'
import {
  RECRUITMENT_CHANNEL_STATUS_LABEL,
} from '@/types'
import type {
  CompanyCandidate,
  RecruitmentChannelStatus,
  RecruitmentMaterialType,
  RecruitmentSourceKind,
  RecruitmentSourceVerification,
} from '@/types'

const SOURCE_KIND_LABEL: Record<RecruitmentSourceKind, string> = {
  official_homepage: '企业官网',
  official_careers: '官方招聘页',
  group_recruitment: '集团招聘平台',
  government_notice: '政府/国资官方公告',
  official_account: '官方公众号',
  official_document: '官方 PDF/图片',
  official_email: '官方招聘邮箱',
  third_party_lead: '第三方待核验线索',
}

const MATERIAL_LABEL: Record<RecruitmentMaterialType, string> = {
  webpage: '网页',
  pdf: 'PDF',
  image: '图片',
  text: '文字',
  email: '邮件',
}

const VERIFICATION_LABEL: Record<RecruitmentSourceVerification, string> = {
  verified_official: '已核验官方来源',
  pending: '待核验',
  rejected: '已排除',
}

interface Props {
  candidate: CompanyCandidate
  onClose: () => void
}

export function CandidateChannelDialog({ candidate, onClose }: Props) {
  const review = useReviewCompanyCandidate()
  const addSource = useAddCandidateSource()
  const sources = useCandidateSources(candidate.id)
  const [channelStatus, setChannelStatus] = useState<RecruitmentChannelStatus>(
    candidate.recruitmentChannelStatus,
  )
  const [officialWebsite, setOfficialWebsite] = useState(candidate.officialWebsite ?? '')
  const [careersUrl, setCareersUrl] = useState(candidate.careersUrl ?? '')
  const [parentCompany, setParentCompany] = useState(candidate.parentCompany ?? '')
  const [groupUrl, setGroupUrl] = useState(candidate.groupRecruitmentUrl ?? '')
  const [attributionKeywords, setAttributionKeywords] = useState(
    candidate.attributionKeywords.join('、') || candidate.name,
  )
  const [note, setNote] = useState(candidate.reviewNote ?? '')

  const [sourceKind, setSourceKind] = useState<RecruitmentSourceKind>('official_document')
  const [verification, setVerification] =
    useState<RecruitmentSourceVerification>('pending')
  const [materialType, setMaterialType] = useState<RecruitmentMaterialType>('webpage')
  const [sourceTitle, setSourceTitle] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [publishedAt, setPublishedAt] = useState('')
  const [sourceContent, setSourceContent] = useState('')
  const [importAsNotice, setImportAsNotice] = useState(false)

  const saveChannel = () => {
    const keywords = attributionKeywords
      .split(/[、,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (channelStatus === 'group_recruitment'
      && (!parentCompany.trim() || !groupUrl.trim() || keywords.length === 0)) {
      toast.error('集团统一招聘需要填写母集团、招聘网址和子公司归属关键词')
      return
    }
    review.mutate(
      {
        id: candidate.id,
        input: {
          decision: candidate.decision === 'monitored'
            ? 'shortlisted'
            : candidate.decision,
          recruitmentChannelStatus: channelStatus,
          officialWebsite: officialWebsite.trim() || null,
          careersUrl: careersUrl.trim() || null,
          parentCompany: channelStatus === 'group_recruitment' ? parentCompany.trim() : null,
          groupRecruitmentUrl: channelStatus === 'group_recruitment' ? groupUrl.trim() : null,
          attributionKeywords: channelStatus === 'group_recruitment' ? keywords : null,
          note: note.trim() || null,
        },
      },
      {
        onSuccess: () => toast.success('招聘渠道状态已保存'),
        onError: (error) => showMutationError('保存招聘渠道失败', error),
      },
    )
  }

  const changeSourceKind = (value: RecruitmentSourceKind) => {
    setSourceKind(value)
    if (value === 'third_party_lead') {
      setVerification('pending')
      setImportAsNotice(false)
    }
  }

  const saveSource = () => {
    if (!sourceTitle.trim()) {
      toast.error('请填写来源标题')
      return
    }
    if (!sourceUrl.trim() && !sourceContent.trim()) {
      toast.error('请填写公开链接或人工摘录正文')
      return
    }
    addSource.mutate(
      {
        id: candidate.id,
        input: {
          sourceKind,
          verificationStatus: sourceKind === 'third_party_lead' ? 'pending' : verification,
          materialType,
          title: sourceTitle.trim(),
          sourceUrl: sourceUrl.trim() || undefined,
          content: sourceContent.trim() || undefined,
          publishedAt: publishedAt.trim() || undefined,
          parentCompany: sourceKind === 'group_recruitment'
            ? parentCompany.trim() || candidate.parentCompany
            : undefined,
          importAsNotice,
        },
      },
      {
        onSuccess: (source) => {
          toast.success(source.importedJobId ? '来源已保存并导入招聘通知' : '招聘来源已保存')
          setSourceTitle('')
          setSourceUrl('')
          setPublishedAt('')
          setSourceContent('')
          setImportAsNotice(false)
        },
        onError: (error) => showMutationError('保存招聘来源失败', error),
      },
    )
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-h-[92vh] overflow-y-auto rounded-xl sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>招聘渠道与来源</DialogTitle>
          <DialogDescription>
            {candidate.name}。没有独立官网或招聘页不等于技术故障；在这里记录真实渠道和可追溯来源。
          </DialogDescription>
        </DialogHeader>

        <section className="space-y-3 rounded-xl border border-black/[0.07] p-4">
          <div>
            <h3 className="text-[13px] font-semibold text-ink">渠道状态</h3>
            <p className="text-[11px] text-ink-tertiary">
              此状态不会被计入 robots 禁止、页面异常或请求失败。
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <Select
              value={channelStatus}
              onValueChange={(value) => setChannelStatus(value as RecruitmentChannelStatus)}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(RECRUITMENT_CHANNEL_STATUS_LABEL) as RecruitmentChannelStatus[])
                  .map((value) => (
                    <SelectItem key={value} value={value}>
                      {RECRUITMENT_CHANNEL_STATUS_LABEL[value]}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
            <Input
              value={officialWebsite}
              onChange={(event) => setOfficialWebsite(event.target.value)}
              placeholder="企业官网（可留空）"
            />
            <Input
              value={careersUrl}
              onChange={(event) => setCareersUrl(event.target.value)}
              placeholder="官方招聘页/公告栏目（可留空）"
            />
            {channelStatus === 'group_recruitment' && (
              <>
                <Input
                  value={parentCompany}
                  onChange={(event) => setParentCompany(event.target.value)}
                  placeholder="母集团名称"
                />
                <Input
                  value={groupUrl}
                  onChange={(event) => setGroupUrl(event.target.value)}
                  placeholder="集团招聘平台网址"
                  className="md:col-span-2"
                />
                <Input
                  value={attributionKeywords}
                  onChange={(event) => setAttributionKeywords(event.target.value)}
                  placeholder="子公司归属关键词，用顿号或逗号分隔"
                  className="md:col-span-2"
                />
              </>
            )}
          </div>
          <Textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="核验备注，例如：官网存在但没有招聘栏目；每月检查一次国资委公告"
          />
          <div className="flex justify-end">
            <Button onClick={saveChannel} disabled={review.isPending}>
              {review.isPending && <Loader2 className="size-4 animate-spin" />}
              保存渠道状态
            </Button>
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-black/[0.07] p-4">
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 size-4 text-brand" />
            <div>
              <h3 className="text-[13px] font-semibold text-ink">登记公开来源</h3>
              <p className="text-[11px] leading-5 text-ink-tertiary">
                PDF、图片或公众号内容可填写公开链接并粘贴人工提取文字。第三方来源始终是待核验线索，不能直接导入岗位事实。
              </p>
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <Select value={sourceKind} onValueChange={(value) => changeSourceKind(value as RecruitmentSourceKind)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(SOURCE_KIND_LABEL) as RecruitmentSourceKind[]).map((value) => (
                  <SelectItem key={value} value={value}>{SOURCE_KIND_LABEL[value]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={materialType} onValueChange={(value) => setMaterialType(value as RecruitmentMaterialType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(Object.keys(MATERIAL_LABEL) as RecruitmentMaterialType[]).map((value) => (
                  <SelectItem key={value} value={value}>{MATERIAL_LABEL[value]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {sourceKind === 'third_party_lead' ? (
              <div className="flex items-center rounded-md bg-warning-soft px-3 text-[12px] text-warning">
                固定为待核验
              </div>
            ) : (
              <Select
                value={verification}
                onValueChange={(value) => {
                  const next = value as RecruitmentSourceVerification
                  setVerification(next)
                  if (next !== 'verified_official') setImportAsNotice(false)
                }}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(Object.keys(VERIFICATION_LABEL) as RecruitmentSourceVerification[]).map((value) => (
                    <SelectItem key={value} value={value}>{VERIFICATION_LABEL[value]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <Input value={sourceTitle} onChange={(event) => setSourceTitle(event.target.value)} placeholder="来源/公告标题" className="md:col-span-2" />
            <Input value={publishedAt} onChange={(event) => setPublishedAt(event.target.value)} placeholder="发布日期（可留空）" />
            <Input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="公开来源链接（可留空）" className="md:col-span-3" />
          </div>
          <Textarea
            value={sourceContent}
            onChange={(event) => setSourceContent(event.target.value)}
            placeholder="粘贴官方通知、PDF/OCR、图片文字或公众号正文；系统不会在这里调用 DeepSeek"
            className="min-h-28"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-[12px] text-ink-body">
              <Switch
                checked={importAsNotice}
                disabled={sourceKind === 'third_party_lead' || verification !== 'verified_official'}
                onCheckedChange={setImportAsNotice}
              />
              同时导入“招聘通知”（仅已核验官方来源）
            </label>
            <Button onClick={saveSource} disabled={addSource.isPending}>
              {addSource.isPending
                ? <Loader2 className="size-4 animate-spin" />
                : <FilePlus2 className="size-4" />}
              保存来源
            </Button>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-[13px] font-semibold text-ink">已登记来源</h3>
          {sources.isLoading ? (
            <p className="text-[12px] text-ink-tertiary">正在读取…</p>
          ) : !sources.data?.length ? (
            <p className="rounded-lg bg-surface-subtle p-3 text-[12px] text-ink-tertiary">
              暂无来源记录。
            </p>
          ) : sources.data.map((source) => (
            <div key={source.id} className="space-y-1 rounded-lg border border-black/[0.06] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium text-ink">{source.title}</span>
                <Pill tone={source.verificationStatus === 'verified_official' ? 'green' : source.verificationStatus === 'rejected' ? 'gray' : 'amber'}>
                  {VERIFICATION_LABEL[source.verificationStatus]}
                </Pill>
                <Pill tone="gray">{SOURCE_KIND_LABEL[source.sourceKind]}</Pill>
                {source.importedJobId && <Pill tone="blue">已导入通知</Pill>}
              </div>
              {source.content && (
                <p className="line-clamp-2 whitespace-pre-wrap text-[11px] leading-5 text-ink-secondary">
                  {source.content}
                </p>
              )}
              {source.sourceUrl && (
                <a href={source.sourceUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-brand hover:underline">
                  打开公开来源 <ExternalLink className="size-3" />
                </a>
              )}
            </div>
          ))}
        </section>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
