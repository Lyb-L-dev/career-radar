import { useLocation } from 'react-router'
import { useListScroll, useUrlSearch } from '@/hooks/useBrowserState'
import { jobDetailHref } from '@/lib/browserState'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  Search,
  Star,
  ExternalLink,
  MoreHorizontal,
  RefreshCw,
  Download,
  RotateCcw,
  Bookmark,
  CircleOff,
  Sparkles,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { SourceNote } from '@/components/jobs/SourceNote'
import { EligibilityBadge } from '@/components/jobs/OfficialAssessment'
import { MatchBadge, JobStatusBadge, Pill } from '@/components/common/Badges'
import { ListSkeleton, EmptyState, ErrorState, NoResults } from '@/components/common/StateViews'
import { useJobs, useJobCounts, useToggleFavorite, useMarkApplied, useMarkNotInterested, useFavoriteMany, useIgnoreJobUpdate, useOfficialScreeningStatus, useStartOfficialScreening } from '@/hooks/useJobs'
import { stopOfficialScreening } from '@/services/jobs'
import { useCompanies } from '@/hooks/useCompanies'
import type { CompanyType, IndustryCategory, Job, JobTab, MatchLevel, JobType } from '@/types'
import { COMPANY_TYPE_LABEL, INDUSTRY_CATEGORY_LABEL, MATCH_LEVEL_LABEL, JOB_TYPE_LABEL } from '@/types'
import { cn } from '@/lib/utils'
import {
  ALL_FILTER_VALUE,
  hasFilterParams,
  jobFilterValuesFromParams,
  jobFilterValuesToParams,
  loadSavedJobFilters,
  saveJobFilters,
  type JobFilterValues,
} from '@/lib/jobFilters'
import { downloadJobsCsv } from '@/lib/jobExport'

const TAB_LABELS: { value: JobTab; label: string }[] = [
  { value: 'recommended', label: '推荐' },
  { value: 'unreviewed', label: '待评估' },
  { value: 'notice', label: '招聘通知' },
  { value: 'new', label: '新增' },
  { value: 'updated', label: '已更新' },
  { value: 'all', label: '全部岗位' },
  { value: 'favorite', label: '收藏' },
]

const ALL = ALL_FILTER_VALUE

export default function JobsPage({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = jobFilterValuesFromParams(params).tab
  const location = useLocation()
  const search = useUrlSearch()
  const from = `${location.pathname}${location.search}`

  const initial = useRef(true)
  useEffect(() => {
    if (!initial.current) return
    initial.current = false
    if (hasFilterParams(params)) return
    const saved = loadSavedJobFilters()
    if (saved) { const next = jobFilterValuesToParams({ ...saved, tab }); next.set('source', 'official'); setParams(next, { replace: true }) }
  }, [params, setParams, tab])
  const urlFilters = jobFilterValuesFromParams(params)
  function setFilter(field: keyof JobFilterValues, value: string) {
    const next = jobFilterValuesToParams({ ...urlFilters, [field]: value })
    next.set('source', 'official')
    setParams(next)
  }
  const keyword = urlFilters.keyword
  const companyId = urlFilters.companyId
  const companyType = urlFilters.companyType
  const industryCategory = urlFilters.industryCategory
  const province = urlFilters.province
  const city = urlFilters.city
  const jobType = urlFilters.jobType
  const ability = urlFilters.ability
  const maxDifficulty = urlFilters.maxDifficulty
  const eligibility = urlFilters.eligibility
  const sort = urlFilters.sort
  const setCompanyId = (value: string) => setFilter('companyId', value)
  const setCompanyType = (value: string) => setFilter('companyType', value)
  const setIndustryCategory = (value: string) => setFilter('industryCategory', value)
  const setProvince = (value: string) => setFilter('province', value)
  const setCity = (value: string) => setFilter('city', value)
  const setJobType = (value: string) => setFilter('jobType', value)
  const setAbility = (value: string) => setFilter('ability', value)
  const setMaxDifficulty = (value: string) => setFilter('maxDifficulty', value)
  const setEligibility = (value: string) => setFilter('eligibility', value)
  const setSort = (value: string) => setFilter('sort', value)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const filter = useMemo(
    () => ({
      tab,
      keyword: keyword || undefined,
      companyId: companyId === ALL ? undefined : companyId,
      companyType: companyType === ALL ? undefined : (companyType as CompanyType),
      industryCategory: industryCategory === ALL ? undefined : (industryCategory as IndustryCategory),
      province: province === ALL ? undefined : province,
      city: city === ALL ? undefined : city,
      type: jobType === ALL ? undefined : (jobType as JobType),
      abilityMatch: ability === ALL ? undefined : (ability as MatchLevel),
      difficultyMax: maxDifficulty === ALL ? undefined : Number(maxDifficulty),
      eligibility: eligibility === ALL ? undefined : eligibility as 'available' | 'eligible' | 'review' | 'ineligible',
      sort: sort as 'priority' | 'updated',
    }),
    [tab, keyword, companyId, companyType, industryCategory, province, city, jobType, ability, maxDifficulty, eligibility, sort],
  )
  const filterValues = useMemo<JobFilterValues>(
    () => ({
      tab,
      keyword,
      companyId,
      companyType,
      industryCategory,
      province,
      city,
      jobType,
      ability,
      maxDifficulty,
      eligibility,
      sort,
    }),
    [tab, keyword, companyId, companyType, industryCategory, province, city, jobType, ability, maxDifficulty, eligibility, sort],
  )

  const { data: jobs, isLoading, isError, refetch, isFetching } = useJobs(filter)
  useListScroll(!isLoading)
  const { data: counts } = useJobCounts()
  const { data: companies } = useCompanies()
  const toggleFav = useToggleFavorite()
  const markApplied = useMarkApplied()
  const markNotInterested = useMarkNotInterested()
  const favoriteMany = useFavoriteMany()
  const ignoreUpdate = useIgnoreJobUpdate()
  const { data: screening } = useOfficialScreeningStatus()
  const screen = useStartOfficialScreening()

  const cities = useMemo(() => Array.from(new Set((jobs ?? []).map((j) => j.city))), [jobs])
  const hasActiveFilter = keyword || companyId !== ALL || companyType !== ALL || industryCategory !== ALL || province !== ALL || city !== ALL || jobType !== ALL || ability !== ALL || maxDifficulty !== ALL || eligibility !== ALL

  const clearFilters = () => { const next = new URLSearchParams({ source: 'official', tab }); setParams(next) }

  const exportJobs = (items: Job[], scope: string) => {
    if (items.length === 0) {
      toast.info('当前没有可导出的岗位')
      return
    }
    const date = new Intl.DateTimeFormat('sv-SE').format(new Date())
    downloadJobsCsv(items, `career-radar-${scope}-${date}.csv`)
    toast.success(`已导出 ${items.length} 个岗位`)
  }

  const toggleSelect = (id: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const allChecked = (jobs?.length ?? 0) > 0 && jobs!.every((j) => selected.has(j.id))

  const rowActions = (job: Job) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="size-8" aria-label="更多操作">
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          onClick={() => {
            markApplied.mutate(
              { id: job.id, applied: !job.isApplied },
              {
                onSuccess: () => toast.success(!job.isApplied ? '已标记为已投递' : '已取消投递标记'),
                onError: (error) => toast.error('操作失败', {
                  description: error instanceof Error ? error.message : '未知错误',
                }),
              },
            )
          }}
        >
          {job.isApplied ? '取消已投递标记' : '标记已投递'}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            markNotInterested.mutate(
              [job.id],
              { onSuccess: () => toast.success('已标记为不感兴趣，后续推荐将减少类似岗位') },
            )
          }}
        >
          标记不感兴趣
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            navigator.clipboard.writeText(`${job.title}｜${job.companyName}｜${job.city}\n${job.sourceUrl}`)
            toast.success('岗位信息已复制')
          }}
        >
          复制岗位信息
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={job.status !== 'updated' || ignoreUpdate.isPending}
          onClick={() => ignoreUpdate.mutate(
            job.id,
            { onSuccess: () => toast.success('已忽略当前版本；岗位再次变化时会重新提醒') },
          )}
        >
          忽略本次更新
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  const listActions = (
    <>
      <Button variant="outline" disabled={screening?.status === 'running' || screen.isPending} onClick={() => screen.mutate({ ids: selected.size ? [...selected] : undefined }, {
        onSuccess: () => toast.success('已开始官网岗位评估，符合或待核对资格的岗位将参与排序'),
        onError: (error) => toast.error(error.message),
      })}>
        {screening?.status === 'running' ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
        {selected.size ? `评估所选 ${selected.size} 条` : 'AI 评估并排序'}
      </Button>
      <Button variant="outline" onClick={() => exportJobs(jobs ?? [], '筛选结果')}>
        <Download className="size-4" />导出结果
      </Button>
      <Button variant="outline" onClick={() => { void refetch(); toast.success('岗位列表已刷新') }} disabled={isFetching}>
        <RefreshCw className={cn('size-4', isFetching && 'animate-spin')} />刷新
      </Button>
    </>
  )

  return (
    <div className="space-y-5">
      {embedded ? <div className="flex flex-wrap justify-end gap-2">{listActions}</div> : <PageHeader
        title="岗位中心"
        subtitle="查看新岗位、岗位变化以及与个人画像的匹配情况"
        actions={listActions}
      />}

      {screening && screening.status !== 'idle' && <div className="rounded-lg bg-surface px-4 py-3 text-sm text-ink-secondary" role="status" aria-live="polite">
        <p>{screening.status === 'running' ? '正在评估' : screening.status === 'completed' ? '本轮评估完成' : screening.status === 'cancelled' ? '已停止评估' : '部分评估未完成'} · {screening.processed}/{screening.total} · AI 新评估 {screening.evaluated} · 复用 {screening.cached} · 资格不符 {screening.ineligible}{screening.skipped > 0 ? ` · 正文不足、公告或版本变化 ${screening.skipped}` : ''}{screening.failed > 0 ? ` · 失败 ${screening.failed}` : ''}</p>
        {screening.currentTitle && <p className="mt-1 break-words">当前：{screening.currentTitle}</p>}
        {screening.error && <p className="mt-1 text-danger">{screening.error}。修复后再次点击评估，会复用已完成结果。</p>}
        {screening.status === 'running' && <Button size="sm" variant="ghost" className="mt-1" onClick={() => { void stopOfficialScreening().then(() => toast.info('当前岗位评估结束后停止')).catch((e: Error) => toast.error(e.message)) }}>停止评估</Button>}
      </div>}

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="official-job-view" className="text-sm font-medium text-ink-secondary">查看</label>
        <Select value={tab} onValueChange={(value) => {
          const next = jobFilterValuesToParams({ ...filterValues, tab: value as JobTab })
          next.set('source', 'official')
          setParams(next)
          setSelected(new Set())
        }}>
          <SelectTrigger id="official-job-view" className="w-44 bg-surface"><SelectValue /></SelectTrigger>
          <SelectContent>
            {TAB_LABELS.map((item) => <SelectItem key={item.value} value={item.value}>{item.label} · {counts?.[item.value] ?? '–'}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={eligibility} onValueChange={setEligibility}>
          <SelectTrigger className="w-44 bg-surface" aria-label="资格筛选"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="available">符合或需要核对</SelectItem>
            <SelectItem value="eligible">资格符合</SelectItem>
            <SelectItem value="review">需要核对</SelectItem>
            <SelectItem value="ineligible">明确不符</SelectItem>
            <SelectItem value={ALL}>全部资格状态</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sort} onValueChange={setSort}>
          <SelectTrigger className="w-44 bg-surface" aria-label="岗位排序"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="priority">投递优先级排序</SelectItem><SelectItem value="updated">最近更新排序</SelectItem></SelectContent>
        </Select>
      </div>

      {/* 搜索筛选 */}
      <Card padded={false} className="p-4 space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
          <Input
            {...search.bind}
            placeholder="搜索职位名称、公司名称、JD 关键词或技能关键词…"
            className="pl-9 h-10 rounded-lg bg-surface-subtle border-black/[0.06]"
          />
        </div>
        <details className="group">
          <summary className="w-fit cursor-pointer text-sm font-medium text-brand-foreground">高级筛选{companyId !== ALL || companyType !== ALL || industryCategory !== ALL || province !== ALL || city !== ALL || jobType !== ALL || ability !== ALL || maxDifficulty !== ALL ? ' · 已启用' : ''}</summary>
        <div className="mt-3 flex flex-wrap items-center gap-2.5">
          <Select value={companyId} onValueChange={setCompanyId}>
            <SelectTrigger className="w-44 h-9 rounded-lg"><SelectValue placeholder="企业" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部企业</SelectItem>
              {(companies ?? []).map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={companyType} onValueChange={setCompanyType}>
            <SelectTrigger className="w-36 h-9 rounded-lg"><SelectValue placeholder="公司类型" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部公司类型</SelectItem>
              {(Object.keys(COMPANY_TYPE_LABEL) as CompanyType[]).map((type) => (
                <SelectItem key={type} value={type}>{COMPANY_TYPE_LABEL[type]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={industryCategory} onValueChange={setIndustryCategory}>
            <SelectTrigger className="w-36 h-9 rounded-lg"><SelectValue placeholder="行业" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部行业</SelectItem>
              {(Object.keys(INDUSTRY_CATEGORY_LABEL) as IndustryCategory[]).map((type) => (
                <SelectItem key={type} value={type}>{INDUSTRY_CATEGORY_LABEL[type]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={province} onValueChange={setProvince}>
            <SelectTrigger className="w-32 h-9 rounded-lg"><SelectValue placeholder="地区" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全国地区</SelectItem>
              <SelectItem value="福建">福建优先</SelectItem>
            </SelectContent>
          </Select>
          <Select value={city} onValueChange={setCity}>
            <SelectTrigger className="w-32 h-9 rounded-lg"><SelectValue placeholder="城市" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部城市</SelectItem>
              {cities.map((c) => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={jobType} onValueChange={setJobType}>
            <SelectTrigger className="w-32 h-9 rounded-lg"><SelectValue placeholder="岗位类型" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>全部类型</SelectItem>
              {(Object.keys(JOB_TYPE_LABEL) as JobType[]).map((t) => (
                <SelectItem key={t} value={t}>{JOB_TYPE_LABEL[t]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={ability} onValueChange={setAbility}>
            <SelectTrigger className="w-36 h-9 rounded-lg"><SelectValue placeholder="能力匹配" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>能力匹配</SelectItem>
              {(Object.keys(MATCH_LEVEL_LABEL) as MatchLevel[]).map((m) => (
                <SelectItem key={m} value={m}>{MATCH_LEVEL_LABEL[m]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={maxDifficulty} onValueChange={setMaxDifficulty}>
            <SelectTrigger className="w-36 h-9 rounded-lg"><SelectValue placeholder="难度上限" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>难度不限</SelectItem>
              <SelectItem value="3">≤ 3 / 10</SelectItem>
              <SelectItem value="5">≤ 5 / 10</SelectItem>
              <SelectItem value="7">≤ 7 / 10</SelectItem>
            </SelectContent>
          </Select>
          {hasActiveFilter ? (
            <Button variant="ghost" size="sm" className="text-ink-secondary" onClick={clearFilters}>
              <RotateCcw className="size-3.5" />
              重置筛选
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            className="text-brand ml-auto"
            onClick={() => {
              saveJobFilters(filterValues)
              toast.success('筛选条件已保存，下次进入岗位中心自动应用')
            }}
          >
            <Bookmark className="size-3.5" />
            保存筛选条件
          </Button>
        </div>
        </details>
      </Card>

      {/* 批量操作条 */}
      {selected.size > 0 && (
        <div className="sticky top-20 z-10 flex items-center gap-3 rounded-xl bg-ink px-4 py-2.5 text-white shadow-pop">
          <span className="text-[13px]">已选择 {selected.size} 个岗位</span>
          <div className="ml-auto flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                const count = selected.size
                favoriteMany.mutate([...selected], {
                  onSuccess: () => {
                    toast.success(`已收藏 ${count} 个岗位`)
                    setSelected(new Set())
                  },
                })
              }}
            >
              <Star className="size-3.5" />
              批量收藏
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                exportJobs((jobs ?? []).filter((job) => selected.has(job.id)), '已选岗位')
                setSelected(new Set())
              }}
            >
              <Download className="size-3.5" />
              批量导出
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                const count = selected.size
                markNotInterested.mutate([...selected], {
                  onSuccess: () => {
                    toast.success(`已将 ${count} 个岗位标记为不感兴趣`)
                    setSelected(new Set())
                  },
                })
              }}
            >
              <CircleOff className="size-3.5" />
              标记不感兴趣
            </Button>
            <Button size="sm" variant="ghost" className="text-white/70 hover:text-white" onClick={() => setSelected(new Set())}>
              取消
            </Button>
          </div>
        </div>
      )}

      {/* 列表 */}
      <Card padded={false}>
        {isLoading ? (
          <div className="p-4"><ListSkeleton rows={6} /></div>
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : !jobs || jobs.length === 0 ? (
          hasActiveFilter ? (
            <NoResults onClear={clearFilters} />
          ) : (
            <EmptyState
              title="暂时没有符合当前条件的岗位。"
              description="还没有发现符合画像的岗位，可以尝试降低匹配条件或添加更多企业。"
              actions={
                <>
                  <Button variant="outline" onClick={clearFilters}>清除筛选条件</Button>
                  <Button variant="outline" onClick={() => navigate('/profile')}>调整求职画像</Button>
                  <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => navigate('/')}>立即扫描企业</Button>
                </>
              }
            />
          )
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-10 pl-4">
                  <Checkbox
                    checked={allChecked}
                    onCheckedChange={(v) => setSelected(v === true ? new Set(jobs.map((j) => j.id)) : new Set())}
                    aria-label="全选"
                  />
                </TableHead>
                <TableHead>职位</TableHead>
                <TableHead className="hidden lg:table-cell">来源</TableHead>
                <TableHead className="hidden lg:table-cell">企业</TableHead>
                <TableHead className="hidden md:table-cell">地点</TableHead>
                <TableHead className="hidden sm:table-cell">匹配度</TableHead>
                <TableHead className="hidden sm:table-cell">资格 / 优先级</TableHead>
                <TableHead className="hidden sm:table-cell">状态</TableHead>
                <TableHead className="w-16 sm:w-24 text-right pr-4">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.id} className={cn(job.notInterested && 'opacity-50')}>
                  <TableCell className="pl-4">
                    <Checkbox
                      checked={selected.has(job.id)}
                      onCheckedChange={(v) => toggleSelect(job.id, v === true)}
                      aria-label={`选择 ${job.title}`}
                    />
                  </TableCell>
                  <TableCell className="max-w-[280px]">
                    <Link to={jobDetailHref(job.id, from)} className="block">
                      <span className="flex items-center gap-1.5 text-[14px] font-medium text-ink hover:text-brand transition-colors">
                        <span className="truncate">{job.title}</span>
                        {job.isFavorite && <Star className="size-3.5 shrink-0 fill-highlight text-highlight" />}
                        {job.isApplied && <Pill tone="blue">已投递</Pill>}
                        {job.type === 'notice' && <Pill tone="blue">官方通知</Pill>}
                        {job.type !== 'notice' && job.abilityMatch === 'unknown' && <Pill tone="amber">待评估</Pill>}
                      </span>
                      {job.recommendReason && (
                        <span className="mt-0.5 block truncate text-[12px] text-ink-tertiary">{job.recommendReason}</span>
                      )}
                      <span className="mt-1 block lg:hidden"><SourceNote kind="official" site={job.source?.site} /></span>
                      <span className="mt-1 flex flex-wrap items-center gap-1 sm:hidden"><EligibilityBadge result={job.eligibility} /><MatchBadge level={job.abilityMatch} />{job.priority && <span className="text-xs text-ink-secondary">{job.priority.label}</span>}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell"><SourceNote kind="official" site={job.source?.site} /></TableCell>
                  <TableCell className="hidden lg:table-cell text-[13px] text-ink-body">{job.companyName}</TableCell>
                  <TableCell className="hidden md:table-cell text-[13px] text-ink-body">{job.city}</TableCell>
                  <TableCell className="hidden sm:table-cell">
                    <div className="flex flex-col gap-1">
                      <MatchBadge level={job.abilityMatch} />
                      <span className="text-[11px] text-ink-tertiary">届别 {MATCH_LEVEL_LABEL[job.gradYearMatch]}</span>
                      <span className="text-[11px] text-ink-tertiary">难度 {job.abilityMatch === 'unknown' || job.difficultyEvaluated === false ? '待评估' : `${job.difficulty}/10`}</span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden sm:table-cell"><EligibilityBadge result={job.eligibility} /><p className="mt-1 text-xs text-ink-secondary">{job.priority?.label}{job.priority?.score !== null && job.priority?.score !== undefined && job.priority.tier !== 'defer' ? ` · ${job.priority.score}` : ''}</p></TableCell>
                  <TableCell className="hidden sm:table-cell"><JobStatusBadge status={job.status} /></TableCell>
                  <TableCell className="pr-4">
                    <div className="flex items-center justify-end gap-0.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn('size-8 text-ink-tertiary', job.isFavorite && 'text-highlight')}
                        aria-label={job.isFavorite ? '取消收藏' : '收藏'}
                        onClick={() => {
                          toggleFav.mutate(
                            job.id,
                            {
                              onSuccess: (res) => toast.success(res.isFavorite ? '岗位已收藏' : '已取消收藏'),
                              onError: (error) => toast.error('操作失败', {
                                description: error instanceof Error ? error.message : '未知错误',
                              }),
                            },
                          )
                        }}
                      >
                        <Star className={cn('size-4', job.isFavorite && 'fill-current')} />
                      </Button>
                      {(job.applyUrl || job.sourceUrl) && (
                        <a href={job.applyUrl || job.sourceUrl} target="_blank" rel="noreferrer" className="hidden sm:block">
                          <Button variant="ghost" size="icon" className="size-8 text-ink-tertiary" aria-label="打开官网">
                            <ExternalLink className="size-4" />
                          </Button>
                        </a>
                      )}
                      {rowActions(job)}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  )
}
