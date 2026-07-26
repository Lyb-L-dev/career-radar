import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Search, Briefcase, Building2, FileText, Activity } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { PageHeader, Card, CardTitle } from '@/components/common/PageHeader'
import { MatchBadge, RunStatusBadge, Pill, CompanyStatusBadge } from '@/components/common/Badges'
import { ListSkeleton, NoResults } from '@/components/common/StateViews'
import { useGlobalSearch } from '@/hooks/useData'

export default function SearchResultsPage() {
  const [params] = useSearchParams()
  const q = params.get('q') ?? ''
  const [input, setInput] = useState(q)
  const navigate = useNavigate()
  const { data, isLoading } = useGlobalSearch(q)

  const total = data ? data.jobs.length + data.companies.length + data.reports.length + data.runs.length : 0

  return (
    <div className="space-y-5">
      <PageHeader title="全局搜索" subtitle={q ? `「${q}」的搜索结果 · 共 ${total} 条` : '输入关键词搜索岗位、企业、日报与运行记录'} />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim()) navigate(`/search?q=${encodeURIComponent(input.trim())}`)
        }}
        className="relative max-w-2xl"
      >
        <Search className="absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-tertiary" />
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="搜索岗位、企业、技能关键词、城市、运行记录…"
          className="h-11 rounded-lg bg-surface pl-10 shadow-card border-black/[0.06]"
          autoFocus
        />
      </form>

      {isLoading ? (
        <ListSkeleton rows={4} card />
      ) : !data || total === 0 ? (
        <Card padded={false}>
          <NoResults onClear={() => setInput('')} />
        </Card>
      ) : (
        <div className="space-y-5">
          {data.jobs.length > 0 && (
            <Card>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <Briefcase className="size-4 text-ink-tertiary" />
                  岗位（{data.jobs.length}）
                </span>
              </CardTitle>
              <ul className="divide-y divide-black/[0.05]">
                {data.jobs.map((j) => (
                  <li key={j.id}>
                    <Link to={`/jobs/${j.id}`} className="flex items-center justify-between gap-3 py-2.5 group">
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-medium text-ink group-hover:text-brand transition-colors">{j.title}</p>
                        <p className="text-[12px] text-ink-tertiary">{j.companyName} · {j.city} · 难度 {j.difficulty}/10</p>
                      </div>
                      <MatchBadge level={j.abilityMatch} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {data.companies.length > 0 && (
            <Card>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <Building2 className="size-4 text-ink-tertiary" />
                  企业（{data.companies.length}）
                </span>
              </CardTitle>
              <ul className="divide-y divide-black/[0.05]">
                {data.companies.map((c) => (
                  <li key={c.id}>
                    <Link to={`/companies/${c.id}`} className="flex items-center justify-between gap-3 py-2.5 group">
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-ink group-hover:text-brand transition-colors">{c.name}</p>
                        <p className="text-[12px] text-ink-tertiary">{c.industry} · {c.website}</p>
                      </div>
                      <CompanyStatusBadge status={c.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {data.reports.length > 0 && (
            <Card>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <FileText className="size-4 text-ink-tertiary" />
                  日报（{data.reports.length}）
                </span>
              </CardTitle>
              <ul className="divide-y divide-black/[0.05]">
                {data.reports.map((r) => (
                  <li key={r.date}>
                    <Link to={`/reports/${r.date}`} className="flex items-center justify-between gap-3 py-2.5 group">
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-ink group-hover:text-brand transition-colors">{r.date} 日报</p>
                        <p className="truncate text-[12px] text-ink-tertiary">{r.summary}</p>
                      </div>
                      <Pill tone="gray">+{r.newJobs} / ↑{r.updatedJobs}</Pill>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {data.runs.length > 0 && (
            <Card>
              <CardTitle>
                <span className="flex items-center gap-2">
                  <Activity className="size-4 text-ink-tertiary" />
                  运行记录（{data.runs.length}）
                </span>
              </CardTitle>
              <ul className="divide-y divide-black/[0.05]">
                {data.runs.map((r) => (
                  <li key={r.id}>
                    <Link to={`/runs/${r.id}`} className="flex items-center justify-between gap-3 py-2.5 group">
                      <div>
                        <p className="text-[14px] font-medium text-ink group-hover:text-brand transition-colors">{r.code}</p>
                        <p className="text-[12px] text-ink-tertiary">{r.startedAt}</p>
                      </div>
                      <RunStatusBadge status={r.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="text-center">
            <Button variant="ghost" className="text-ink-tertiary" onClick={() => navigate(-1)}>
              返回上一页
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
