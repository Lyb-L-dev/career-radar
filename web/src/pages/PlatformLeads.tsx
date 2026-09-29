import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ArrowUpRight, Bookmark, Check, EyeOff, FileJson, RefreshCw, Sparkles } from 'lucide-react'
import { apiRequest, USE_MOCK } from '@/services/config'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/common/StateViews'

type Category = 'priority' | 'review' | 'lower' | 'excluded'
type StateField = 'favorite' | 'applied' | 'hidden'

interface AIScreenResult {
  eligibility: 'eligible' | 'ineligible' | 'unknown'
  fit: 'strong' | 'reasonable' | 'weak' | 'unknown'
  action: 'prioritize' | 'consider' | 'defer'
  confidence: 'high' | 'medium' | 'low'
  summary: string
  eligibility_checks: {
    requirement: string
    verdict: 'met' | 'unmet' | 'unknown'
    job_quote: string
    candidate_quote: string
  }[]
  matched_evidence: string[]
  gaps: string[]
  next_step: string
}

interface PlatformLead {
  id: string
  title: string
  company: string
  location: string
  salary: string
  tags: string
  description: string
  source_url: string
  jdComplete: boolean
  companyIdentified: boolean
  aiScreenable: boolean
  firstSeenAt: string
  lastSeenAt: string
  isFavorite: boolean
  isApplied: boolean
  isHidden: boolean
  score: number
  category: Category
  reasons: string[]
  blockers: string[]
  aiResult: AIScreenResult | null
  aiCheckedAt: string | null
  aiNeedsRefresh: boolean
}

interface ImportPreview {
  total: number
  completeJd: number
  needsReview: number
}

interface ImportResult {
  total: number
  new: number
  updated: number
  unchanged: number
}

interface BossPreferences {
  currentStudent: boolean | null
  acceptInternship: boolean
}

const CATEGORIES: { value: Category | 'all'; label: string }[] = [
  { value: 'priority', label: '优先阅读' },
  { value: 'review', label: '需确认' },
  { value: 'lower', label: '低优先级' },
  { value: 'excluded', label: '已排除' },
  { value: 'all', label: '全部' },
]

const CATEGORY_LABEL: Record<Category, string> = {
  priority: '优先阅读',
  review: '需确认',
  lower: '低优先级',
  excluded: '已排除',
}

const ELIGIBILITY_LABEL = {
  eligible: 'AI 判断：报名条件基本符合',
  ineligible: 'AI 提示资格不符，请核对原文',
  unknown: '报名资格仍需确认',
}

const FIT_LABEL = {
  strong: '方向高度相关',
  reasonable: '方向可考虑',
  weak: '方向匹配较弱',
  unknown: '方向信息不足',
}

const ACTION_LABEL = {
  prioritize: '建议优先核对并投递',
  consider: '建议阅读后决定',
  defer: '建议暂缓',
}

function localDate(value: string): string {
  return new Date(value).toLocaleDateString('zh-CN')
}

export default function PlatformLeadsPage() {
  const [leads, setLeads] = useState<PlatformLead[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [content, setContent] = useState('')
  const [filename, setFilename] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [category, setCategory] = useState<Category | 'all'>('priority')
  const [keyword, setKeyword] = useState('')
  const [includeHandled, setIncludeHandled] = useState(false)
  const [preferences, setPreferences] = useState<BossPreferences | null>(null)
  const [preferencesBusy, setPreferencesBusy] = useState(false)
  const [workingId, setWorkingId] = useState<string | null>(null)
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null)
  const stopAfterCurrent = useRef(false)

  const load = useCallback(async (silent = false) => {
    if (USE_MOCK) {
      setLoading(false)
      return
    }
    if (!silent) setLoading(true)
    try {
      const [items, currentPreferences] = await Promise.all([
        apiRequest<PlatformLead[]>('/platform-leads'),
        apiRequest<BossPreferences>('/platform-leads/preferences'),
      ])
      setLeads(items)
      setPreferences(currentPreferences)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '加载失败')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])
  useEffect(() => () => { stopAfterCurrent.current = true }, [])

  const visible = useMemo(() => leads.filter((lead) => {
    if (category !== 'all' && lead.category !== category) return false
    if (!includeHandled && (lead.isHidden || lead.isApplied)) return false
    const query = keyword.trim().toLocaleLowerCase()
    if (query && !`${lead.title} ${lead.company} ${lead.description}`.toLocaleLowerCase().includes(query)) return false
    return true
  }), [leads, category, keyword, includeHandled])

  const counts = useMemo(() => Object.fromEntries(
    CATEGORIES.map((item) => [item.value, leads.filter((lead) =>
      item.value === 'all' || lead.category === item.value
    ).length])
  ), [leads])

  const aiQueue = useMemo(() => leads.filter((lead) =>
    lead.aiScreenable && !lead.isApplied && !lead.isHidden &&
    lead.category !== 'excluded' && !lead.aiResult
  ).slice(0, 20), [leads])

  async function requestScreen(leadId: string): Promise<void> {
    await apiRequest(`/platform-leads/${encodeURIComponent(leadId)}/ai-screen`, {
      method: 'POST', body: JSON.stringify({ confirmed: true }),
    })
    await load(true)
  }

  async function screenOne(leadId: string) {
    if (workingId || batchProgress) return
    setWorkingId(leadId)
    try {
      await requestScreen(leadId)
      toast.success('AI 筛选已完成，请核对原始 JD 与报名条件')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'AI 筛选失败')
    } finally {
      setWorkingId(null)
    }
  }

  async function screenBatch() {
    if (workingId || batchProgress || aiQueue.length === 0) return
    const queue = [...aiQueue]
    stopAfterCurrent.current = false
    setBatchProgress({ done: 0, total: queue.length })
    let done = 0
    for (const lead of queue) {
      if (stopAfterCurrent.current) break
      setWorkingId(lead.id)
      try {
        await requestScreen(lead.id)
        done += 1
        setBatchProgress({ done, total: queue.length })
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : 'AI 筛选失败，已停止本批')
        break
      }
    }
    setWorkingId(null)
    setBatchProgress(null)
    if (done > 0) toast.success(`本次完成 ${done} 条 AI 筛选`)
  }

  async function chooseFile(file: File | undefined) {
    setContent('')
    setPreview(null)
    setFilename('')
    if (!file) return
    if (file.size > 5_000_000) {
      toast.error('单个 JSON 文件最多 5 MB，请分批导入')
      return
    }
    setBusy(true)
    try {
      const text = await file.text()
      const result = await apiRequest<ImportPreview>('/platform-leads/preview', {
        method: 'POST', body: JSON.stringify({ content: text }),
      })
      setContent(text)
      setPreview(result)
      setFilename(file.name)
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '无法预览文件')
    } finally {
      setBusy(false)
    }
  }

  async function savePreferences(next: BossPreferences) {
    setPreferencesBusy(true)
    try {
      const saved = await apiRequest<BossPreferences>('/platform-leads/preferences', {
        method: 'PUT', body: JSON.stringify(next),
      })
      setPreferences(saved)
      await load(true)
      toast.success('求职身份已更新，岗位与 AI 判断已按新条件重算')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '求职身份保存失败')
    } finally {
      setPreferencesBusy(false)
    }
  }

  async function importFile() {
    if (!content) return
    setBusy(true)
    try {
      const result = await apiRequest<ImportResult>('/platform-leads/import', {
        method: 'POST', body: JSON.stringify({ content }),
      })
      toast.success(`导入完成：新增 ${result.new}，更新 ${result.updated}，未变化 ${result.unchanged}`)
      setContent('')
      setPreview(null)
      setFilename('')
      await load()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '导入失败')
    } finally {
      setBusy(false)
    }
  }

  async function toggleState(lead: PlatformLead, field: StateField) {
    const current = field === 'favorite' ? lead.isFavorite : field === 'applied' ? lead.isApplied : lead.isHidden
    try {
      await apiRequest(`/platform-leads/${encodeURIComponent(lead.id)}/state`, {
        method: 'POST', body: JSON.stringify({ field, value: !current }),
      })
      await load()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '状态保存失败')
    }
  }

  if (USE_MOCK) {
    return <EmptyState title="平台机会池需要本地后端" description="请启动 Career Radar 本地服务后导入 BOSS JSON 文件。" />
  }

  return (
    <div className="min-w-0 max-w-full space-y-6 overflow-x-hidden">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">平台机会池</h1>
        <p className="max-w-2xl text-sm leading-6 text-ink-secondary">
          集中查看 AI/FDE 岗位，校招和应届优先。这里的职位来自 BOSS 平台，投递前可打开原始页面核对。
        </p>
      </header>

      <Card className="gap-3 p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <FileJson className="mt-0.5 size-5 shrink-0 text-brand-foreground" />
            <div className="min-w-0">
              <h2 className="font-semibold text-ink">导入 BOSS 抓取结果</h2>
              <p className="text-xs leading-5 text-ink-secondary">
                支持 boss-zhipin-scraper 导出的职位列表或详情 JSON；文件只上传到本机 Career Radar。{' '}
                <a href="https://github.com/eatmoreduck/boss-zhipin-scraper" target="_blank" rel="noreferrer" className="text-brand-foreground underline-offset-2 hover:underline">查看抓取工具</a>
              </p>
            </div>
          </div>
          <Input
            id="boss-json-file"
            type="file"
            accept=".json,application/json"
            aria-label="选择 BOSS 职位 JSON 文件"
            className="sr-only"
            onChange={(event) => { void chooseFile(event.target.files?.[0]) }}
          />
          <Button asChild variant="outline" className="w-full sm:w-auto"><label htmlFor="boss-json-file" className="cursor-pointer">选择 JSON 文件</label></Button>
        </div>
        {preview && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg bg-brand-soft p-3 text-sm">
            <span className="font-medium">{filename}</span>
            <span>共 {preview.total} 条</span>
            <span>完整 JD {preview.completeJd} 条</span>
            <span>需确认 {preview.needsReview} 条</span>
            <Button size="sm" onClick={() => { void importFile() }} disabled={busy}>确认导入</Button>
          </div>
        )}
      </Card>

      {preferences && (
        <div className="flex flex-col items-stretch gap-4 rounded-xl border bg-surface p-4 sm:flex-row sm:items-center">
          <div className="w-full min-w-0 sm:flex-1">
            <p className="text-sm font-semibold text-ink">你的当前求职身份</p>
            <p className="text-xs text-ink-secondary">已毕业时排除明确要求在校生的岗位；关闭实习后保留应届正式岗和初级社招。</p>
          </div>
          <label className="flex w-full items-center justify-between gap-2 text-sm text-ink-secondary sm:w-auto sm:justify-start">
            在校状态
            <select
              value={preferences.currentStudent === null ? 'unknown' : preferences.currentStudent ? 'student' : 'graduated'}
              disabled={preferencesBusy}
              onChange={(event) => { void savePreferences({
                ...preferences,
                currentStudent: event.target.value === 'unknown' ? null : event.target.value === 'student',
              }) }}
              className="h-9 rounded-lg border bg-surface px-3 text-ink"
            >
              <option value="unknown">待确认</option>
              <option value="graduated">已毕业</option>
              <option value="student">仍在校</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            <input
              type="checkbox"
              checked={preferences.acceptInternship}
              disabled={preferencesBusy}
              onChange={(event) => { void savePreferences({ ...preferences, acceptInternship: event.target.checked }) }}
            />
            接受实习岗位
          </label>
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-xl bg-brand-soft p-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <Sparkles className="mt-0.5 size-5 shrink-0 text-brand-foreground" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">AI 二次筛选</p>
            <p className="text-xs leading-5 text-ink-secondary">
              先跳过已排除或缺完整 JD 的职位，再逐条调用当前小米 MiMo 配置；每次最多 20 条。
              发送岗位 JD 与不含联系方式的求职画像，结果会按 JD、画像和模型版本缓存。
            </p>
          </div>
        </div>
        {batchProgress ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-ink-secondary">已完成 {batchProgress.done}/{batchProgress.total}</span>
            <Button size="sm" variant="outline" onClick={() => { stopAfterCurrent.current = true }}>
              当前条完成后停止
            </Button>
          </div>
        ) : (
          <Button size="sm" className="w-full sm:w-auto" disabled={aiQueue.length === 0 || workingId !== null} onClick={() => { void screenBatch() }}>
            <Sparkles className="size-4" />筛选待看岗位 {aiQueue.length} 条
          </Button>
        )}
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {CATEGORIES.map((item) => (
            <Button
              key={item.value}
              size="sm"
              variant={category === item.value ? 'default' : 'outline'}
              onClick={() => setCategory(item.value)}
            >
              {item.label} {counts[item.value] ?? 0}
            </Button>
          ))}
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => { void load() }} aria-label="刷新机会">
            <RefreshCw className="size-4" />
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索岗位、公司或 JD"
            className="max-w-md"
          />
          <label className="flex items-center gap-2 text-sm text-ink-secondary">
            <input type="checkbox" checked={includeHandled} onChange={(event) => setIncludeHandled(event.target.checked)} />
            显示已投递和已隐藏
          </label>
        </div>
        <p className="text-xs text-ink-tertiary">分数只决定阅读顺序；“首次见到”是本机首次导入日期，并非 BOSS 发布日期。</p>
      </section>

      {loading ? <ListSkeleton card /> : error ? <ErrorState description={error} onRetry={() => { void load() }} /> : visible.length === 0 ? (
        <EmptyState title={leads.length ? '当前筛选下没有机会' : '还没有导入 BOSS 职位'}
          description={leads.length ? '切换分组、显示已处理岗位或换个关键词。' : '先用已登录的 BOSS 浏览器导出 JSON，再在上方导入。'} />
      ) : (
        <div className="space-y-3">
          {visible.map((lead) => (
            <Card key={lead.id} className="gap-3 p-5">
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-ink">{lead.title}</h2>
                    <Badge variant={lead.category === 'excluded' ? 'destructive' : 'secondary'}>{CATEGORY_LABEL[lead.category]}</Badge>
                    {!lead.jdComplete && <Badge variant="outline">JD 待确认</Badge>}
                    {!lead.companyIdentified && <Badge variant="outline">招聘方待核对</Badge>}
                    {lead.jdComplete && !lead.aiScreenable && <Badge variant="outline">JD 较长，请人工核对</Badge>}
                    {lead.isApplied && <Badge variant="outline">已投递</Badge>}
                  </div>
                  <p className="mt-1 text-sm text-ink-secondary">
                    {lead.company || '公司待确认'} · {lead.location || '地点未提供'} · {lead.salary || '薪资未提供'}
                  </p>
                </div>
                <span className="rounded-lg bg-brand-soft px-3 py-1.5 text-sm font-semibold text-brand-foreground" title="阅读优先级，并非录取概率">
                  阅读排序 {lead.score}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">BOSS直聘 · 平台线索</Badge>
                {lead.tags && <Badge variant="outline">{lead.tags}</Badge>}
                <span className="self-center text-xs text-ink-tertiary">
                  首次见到 {localDate(lead.firstSeenAt)} · 最近见到 {localDate(lead.lastSeenAt)}
                </span>
              </div>
              <div className="space-y-1 text-sm text-ink-secondary">
                {lead.blockers.map((reason) => <p key={reason} className="text-danger">{reason}</p>)}
                {lead.reasons.slice(0, 3).map((reason) => <p key={reason}>· {reason}</p>)}
              </div>
              {lead.description && (
                <details className="rounded-lg bg-surface-subtle p-3 text-sm">
                  <summary className="cursor-pointer font-medium">查看完整 JD</summary>
                  <pre className="mt-3 whitespace-pre-wrap break-words font-sans leading-6">{lead.description}</pre>
                </details>
              )}
              {lead.aiResult ? (
                <div className="min-w-0 space-y-2 break-words rounded-lg bg-brand-soft p-4 text-sm">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">{ELIGIBILITY_LABEL[lead.aiResult.eligibility]}</Badge>
                    <Badge variant="outline">{FIT_LABEL[lead.aiResult.fit]}</Badge>
                    <Badge variant="outline">{ACTION_LABEL[lead.aiResult.action]}</Badge>
                    <span className="self-center text-xs text-ink-tertiary">
                      AI 分析于 {lead.aiCheckedAt ? localDate(lead.aiCheckedAt) : '最近'} · 非录用保证
                    </span>
                  </div>
                  <p className="leading-6 text-ink">{lead.aiResult.summary}</p>
                  {lead.aiResult.eligibility_checks.length > 0 && (
                    <details>
                      <summary className="cursor-pointer text-xs font-medium text-brand-foreground">查看资格判断依据</summary>
                      <ul className="mt-2 space-y-1 text-xs text-ink-secondary">
                        {lead.aiResult.eligibility_checks.map((check, index) => (
                          <li key={index}>
                            {check.requirement}：{check.verdict === 'met' ? '符合' : check.verdict === 'unmet' ? '不符合' : '待确认'}
                            {check.job_quote && ` · JD「${check.job_quote}」`}
                            {check.candidate_quote && ` · 画像「${check.candidate_quote}」`}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {lead.aiResult.matched_evidence.length > 0 && <p className="text-xs text-ink-secondary">已有证据：{lead.aiResult.matched_evidence.join('、')}</p>}
                  {lead.aiResult.gaps.length > 0 && <p className="text-xs text-ink-secondary">仍需确认：{lead.aiResult.gaps.join('；')}</p>}
                  <p className="text-xs text-ink-secondary">下一步：{lead.aiResult.next_step}</p>
                  {lead.aiResult.fit === 'weak' && (
                    <p className="text-xs text-ink-secondary">
                      判断只依据当前画像。如果你有尚未记录的真实 AI/Agent 项目，
                      <Link to="/profile" className="text-brand-foreground underline-offset-2 hover:underline">先补充画像证据</Link>，岗位会自动显示为需要重新评估。
                    </p>
                  )}
                </div>
              ) : lead.aiNeedsRefresh ? (
                <p className="text-xs text-ink-secondary">岗位、画像或模型已变化，原 AI 结果已失效。</p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {lead.aiScreenable && lead.category !== 'excluded' && !lead.aiResult && (
                  <Button size="sm" variant="outline" disabled={workingId !== null || batchProgress !== null} onClick={() => { void screenOne(lead.id) }}>
                    <Sparkles className="size-4" />
                    {workingId === lead.id ? '分析中…' : lead.aiNeedsRefresh ? '更新 AI 判断' : 'AI 判断能否投'}
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => { void toggleState(lead, 'favorite') }}>
                  <Bookmark className="size-4" />{lead.isFavorite ? '已收藏' : '收藏'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => { void toggleState(lead, 'applied') }}>
                  <Check className="size-4" />{lead.isApplied ? '取消已投递' : '标记已投递'}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => { void toggleState(lead, 'hidden') }}>
                  <EyeOff className="size-4" />{lead.isHidden ? '恢复' : '不感兴趣'}
                </Button>
                <Button size="sm" asChild>
                  <a href={lead.source_url} target="_blank" rel="noreferrer">
                    去 BOSS 查看 <ArrowUpRight className="size-4" />
                  </a>
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
