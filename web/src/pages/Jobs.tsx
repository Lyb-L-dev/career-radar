import { useMemo, useState } from 'react'
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
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { MatchBadge, JobStatusBadge, DifficultyMeter, Pill } from '@/components/common/Badges'
import { ListSkeleton, EmptyState, ErrorState, NoResults } from '@/components/common/StateViews'
import { useJobs, useJobCounts, useToggleFavorite, useMarkApplied, useMarkNotInterested, useFavoriteMany } from '@/hooks/useJobs'
import { useCompanies } from '@/hooks/useCompanies'
import type { CompanyType, IndustryCategory, Job, JobTab, MatchLevel, JobType } from '@/types'
import { COMPANY_TYPE_LABEL, INDUSTRY_CATEGORY_LABEL, MATCH_LEVEL_LABEL, JOB_TYPE_LABEL } from '@/types'
import { cn } from '@/lib/utils'

const TAB_LABELS: { value: JobTab; label: string }[] = [
  { value: 'recommended', label: '推荐' },
  { value: 'notice', label: '招聘通知' },
  { value: 'new', label: '新增' },
  { value: 'updated', label: '已更新' },
  { value: 'all', label: '全部岗位' },
  { value: 'favorite', label: '收藏' },
]

const ALL = '__all__'

export default function JobsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const tab = (params.get('tab') as JobTab) || 'recommended'

  const [keyword, setKeyword] = useState('')
  const [companyId, setCompanyId] = useState(ALL)
  const [companyType, setCompanyType] = useState(ALL)
  const [industryCategory, setIndustryCategory] = useState(ALL)
  const [province, setProvince] = useState(ALL)
  const [city, setCity] = useState(ALL)
  const [jobType, setJobType] = useState(ALL)
  const [ability, setAbility] = useState(ALL)
  const [maxDifficulty, setMaxDifficulty] = useState(ALL)
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
    }),
    [tab, keyword, companyId, companyType, industryCategory, province, city, jobType, ability, maxDifficulty],
  )

  const { data: jobs, isLoading, isError, refetch, isFetching } = useJobs(filter)
  const { data: counts } = useJobCounts()
  const { data: companies } = useCompanies()
  const toggleFav = useToggleFavorite()
  const markApplied = useMarkApplied()
  const markNotInterested = useMarkNotInterested()
  const favoriteMany = useFavoriteMany()

  const cities = useMemo(() => Array.from(new Set((jobs ?? []).map((j) => j.city))), [jobs])
  const hasActiveFilter = keyword || companyId !== ALL || companyType !== ALL || industryCategory !== ALL || province !== ALL || city !== ALL || jobType !== ALL || ability !== ALL || maxDifficulty !== ALL

  const clearFilters = () => {
    setKeyword('')
    setCompanyId(ALL)
    setCompanyType(ALL)
    setIndustryCategory(ALL)
    setProvince(ALL)
    setCity(ALL)
    setJobType(ALL)
    setAbility(ALL)
    setMaxDifficulty(ALL)
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
            markApplied.mutate({ id: job.id, applied: !job.isApplied })
            toast.success(job.isApplied ? '已取消投递标记' : '已标记为已投递')
          }}
        >
          {job.isApplied ? '取消已投递标记' : '标记已投递'}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            markNotInterested.mutate([job.id])
            toast.success('已标记为不感兴趣，后续推荐将减少类似岗位')
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
        <DropdownMenuItem onClick={() => toast.success('已忽略本次更新')}>忽略本次更新</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title="岗位中心"
        subtitle="查看新岗位、岗位变化以及与个人画像的匹配情况"
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => toast.success('当前筛选结果已导出为 CSV 文件')}
            >
              <Download className="size-4" />
              导出当前结果
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                refetch()
                toast.success('岗位列表已刷新')
              }}
              disabled={isFetching}
            >
              <RefreshCw className={cn('size-4', isFetching && 'animate-spin')} />
              刷新岗位
            </Button>
          </>
        }
      />

      {/* 标签页 */}
      <Tabs value={tab} onValueChange={(v) => { setParams({ tab: v }); setSelected(new Set()) }}>
        <TabsList className="bg-surface shadow-card h-11 rounded-lg p-1">
          {TAB_LABELS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} className="rounded-md px-4 data-[state=active]:bg-brand-soft data-[state=active]:text-brand-foreground data-[state=active]:shadow-none">
              {t.label}
              <span className="ml-1.5 text-[12px] text-ink-tertiary data-[state=active]:text-brand-foreground">
                {counts?.[t.value] ?? '–'}
              </span>
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {/* 搜索筛选 */}
      <Card padded={false} className="p-4 space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="搜索职位名称、公司名称、JD 关键词或技能关键词…"
            className="pl-9 h-10 rounded-lg bg-surface-subtle border-black/[0.06]"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
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
            onClick={() => toast.success('筛选条件已保存，下次进入岗位中心自动应用')}
          >
            <Bookmark className="size-3.5" />
            保存筛选条件
          </Button>
        </div>
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
                favoriteMany.mutate([...selected])
                toast.success(`已收藏 ${selected.size} 个岗位`)
                setSelected(new Set())
              }}
            >
              <Star className="size-3.5" />
              批量收藏
            </Button>
            <Button size="sm" variant="secondary" onClick={() => { toast.success(`已导出 ${selected.size} 个岗位`); setSelected(new Set()) }}>
              <Download className="size-3.5" />
              批量导出
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                markNotInterested.mutate([...selected])
                toast.success(`已将 ${selected.size} 个岗位标记为不感兴趣`)
                setSelected(new Set())
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
                <TableHead className="hidden lg:table-cell">企业</TableHead>
                <TableHead className="hidden md:table-cell">地点</TableHead>
                <TableHead>匹配度</TableHead>
                <TableHead className="hidden md:table-cell">难度</TableHead>
                <TableHead className="hidden sm:table-cell">状态</TableHead>
                <TableHead className="hidden xl:table-cell">更新时间</TableHead>
                <TableHead className="w-24 text-right pr-4">操作</TableHead>
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
                    <Link to={`/jobs/${job.id}`} className="block">
                      <span className="flex items-center gap-1.5 text-[14px] font-medium text-ink hover:text-brand transition-colors">
                        <span className="truncate">{job.title}</span>
                        {job.isFavorite && <Star className="size-3.5 shrink-0 fill-highlight text-highlight" />}
                        {job.isApplied && <Pill tone="blue">已投递</Pill>}
                        {job.type === 'notice' && <Pill tone="blue">官方通知</Pill>}
                      </span>
                      {job.recommendReason && (
                        <span className="mt-0.5 block truncate text-[12px] text-ink-tertiary">{job.recommendReason}</span>
                      )}
                    </Link>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-[13px] text-ink-body">{job.companyName}</TableCell>
                  <TableCell className="hidden md:table-cell text-[13px] text-ink-body">{job.city}</TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      <MatchBadge level={job.abilityMatch} />
                      <span className="text-[11px] text-ink-tertiary">届别 {MATCH_LEVEL_LABEL[job.gradYearMatch]}</span>
                    </div>
                  </TableCell>
                  <TableCell className="hidden md:table-cell"><DifficultyMeter value={job.difficulty} /></TableCell>
                  <TableCell className="hidden sm:table-cell"><JobStatusBadge status={job.status} /></TableCell>
                  <TableCell className="hidden xl:table-cell text-[12px] text-ink-tertiary tabular-nums">{job.lastUpdatedAt.slice(5, 16)}</TableCell>
                  <TableCell className="pr-4">
                    <div className="flex items-center justify-end gap-0.5">
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn('size-8 text-ink-tertiary', job.isFavorite && 'text-highlight')}
                        aria-label={job.isFavorite ? '取消收藏' : '收藏'}
                        onClick={() => {
                          toggleFav.mutate(job.id)
                          toast.success(job.isFavorite ? '已取消收藏' : '岗位已收藏')
                        }}
                      >
                        <Star className={cn('size-4', job.isFavorite && 'fill-current')} />
                      </Button>
                      {(job.applyUrl || job.sourceUrl) && (
                        <a href={job.applyUrl || job.sourceUrl} target="_blank" rel="noreferrer">
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
