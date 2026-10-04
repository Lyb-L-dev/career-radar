import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SourceNote } from '@/components/jobs/SourceNote'
import { useJobs } from '@/hooks/useJobs'
import { apiRequest, USE_MOCK } from '@/services/config'
import { MATCH_LEVEL_LABEL } from '@/types'

interface BossLeadSummary {
  id: string
  title: string
  company: string
  location: string
  description: string
  category: 'priority' | 'review' | 'lower' | 'excluded'
  isApplied: boolean
  isHidden: boolean
  lastSeenAt: string
}

interface OpportunityRow {
  key: string
  kind: 'official' | 'boss'
  title: string
  company: string
  location: string
  site?: string
  status: string
  seenAt: string
  href: string
  searchable: string
  filteredOut: boolean
}

export default function UnifiedJobsPage() {
  const [keyword, setKeyword] = useState('')
  const [showFilteredOut, setShowFilteredOut] = useState(false)
  const [visibleCount, setVisibleCount] = useState(60)
  const official = useJobs({ tab: 'all' })
  const boss = useQuery({
    queryKey: ['platform-leads', 'job-hub'],
    queryFn: () => USE_MOCK ? Promise.resolve([] as BossLeadSummary[]) : apiRequest<BossLeadSummary[]>('/platform-leads'),
  })

  const rows = useMemo(() => {
    const fromOfficial: OpportunityRow[] = (official.data ?? []).map((job) => ({
      key: `official:${job.id}`,
      kind: 'official',
      title: job.title,
      company: job.companyName,
      location: job.city,
      site: job.source?.site,
      status: job.isApplied ? '已投递' : job.type === 'notice' ? '招聘通知' : MATCH_LEVEL_LABEL[job.abilityMatch],
      seenAt: job.lastUpdatedAt,
      href: `/jobs/${encodeURIComponent(job.id)}`,
      searchable: `${job.title} ${job.companyName} ${job.city}`.toLocaleLowerCase(),
      filteredOut: job.status === 'closed' || job.notInterested,
    }))
    const fromBoss: OpportunityRow[] = (boss.data ?? []).map((lead) => ({
      key: `boss:${lead.id}`,
      kind: 'boss',
      title: lead.title,
      company: lead.company || '招聘方待核对',
      location: lead.location || '地点未提供',
      status: lead.isApplied ? '已投递' : lead.category === 'priority' ? '优先阅读' : lead.category === 'review' ? '需确认' : lead.category === 'lower' ? '低优先级' : '已排除',
      seenAt: lead.lastSeenAt,
      href: `/jobs?source=boss&lead=${encodeURIComponent(lead.id)}`,
      searchable: `${lead.title} ${lead.company} ${lead.location} ${lead.description}`.toLocaleLowerCase(),
      filteredOut: lead.category === 'excluded' || lead.isHidden,
    }))
    const query = keyword.trim().toLocaleLowerCase()
    return [...fromOfficial, ...fromBoss]
      .filter((row) => (showFilteredOut || !row.filteredOut) && (!query || row.searchable.includes(query)))
      .sort((a, b) => b.seenAt.localeCompare(a.seenAt))
  }, [official.data, boss.data, keyword, showFilteredOut])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[260px] flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
          <Input value={keyword} onChange={(event) => { setKeyword(event.target.value); setVisibleCount(60) }} placeholder="搜索岗位或公司" aria-label="搜索全部岗位" className="h-10 bg-surface pl-9" />
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-secondary">
          <input type="checkbox" checked={showFilteredOut} onChange={(event) => { setShowFilteredOut(event.target.checked); setVisibleCount(60) }} />
          显示已排除、关闭和隐藏
        </label>
      </div>
      {official.isError && <p role="alert" className="text-sm text-danger">官网岗位加载失败；下方仍显示已取得的平台线索。刷新页面可重试。</p>}
      {boss.isError && <p role="alert" className="text-sm text-danger">BOSS 线索加载失败；下方仍显示已取得的官网岗位。刷新页面可重试。</p>}
      {official.isLoading && boss.isLoading ? (
        <p className="py-12 text-center text-sm text-ink-secondary">正在加载岗位…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl bg-surface px-5 py-10 text-center text-sm text-ink-secondary">当前没有符合条件的岗位。试试更短的关键词，或显示已排除和关闭的岗位。</p>
      ) : (
        <div className="overflow-hidden rounded-xl bg-surface">
          <div className="flex items-center justify-between border-b border-black/[0.06] px-5 py-3 text-xs text-ink-secondary">
            <span>找到 {rows.length} 条 · 企业招聘页 {rows.filter((row) => row.kind === 'official').length} · BOSS直聘 {rows.filter((row) => row.kind === 'boss').length}</span>
            <span>按本机最近见到时间排序</span>
          </div>
          <ul className="divide-y divide-black/[0.06]">
            {rows.slice(0, visibleCount).map((row) => (
              <li key={row.key}>
                <Link to={row.href} className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-3.5 transition-colors hover:bg-black/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">
                  <div className="min-w-[240px] flex-1">
                    <p className="truncate text-sm font-medium text-ink">{row.title}</p>
                    <p className="mt-0.5 truncate text-xs text-ink-secondary">{row.company} · {row.location}</p>
                  </div>
                  <SourceNote kind={row.kind} site={row.site} />
                  <span className="w-20 text-xs text-ink-secondary">{row.status}</span>
                  <span className="w-24 text-right text-xs tabular-nums text-ink-tertiary">{row.seenAt.slice(0, 10)}</span>
                </Link>
              </li>
            ))}
          </ul>
          {rows.length > visibleCount && <div className="border-t border-black/[0.06] p-3 text-center"><Button variant="ghost" size="sm" onClick={() => setVisibleCount((count) => count + 60)}>显示更多</Button></div>}
        </div>
      )}
    </div>
  )
}
