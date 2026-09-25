import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ArrowUpRight, Bookmark, Check, EyeOff, FileJson, RefreshCw } from 'lucide-react'
import { apiRequest, USE_MOCK } from '@/services/config'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/common/StateViews'

type Category = 'priority' | 'review' | 'lower' | 'excluded'
type StateField = 'favorite' | 'applied' | 'hidden'

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
  firstSeenAt: string
  lastSeenAt: string
  isFavorite: boolean
  isApplied: boolean
  isHidden: boolean
  score: number
  category: Category
  reasons: string[]
  blockers: string[]
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

  const load = useCallback(async () => {
    if (USE_MOCK) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      setLeads(await apiRequest<PlatformLead[]>('/platform-leads'))
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

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
    <div className="space-y-6">
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
              <div className="flex flex-wrap gap-2">
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
