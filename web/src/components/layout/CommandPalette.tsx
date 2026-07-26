import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from '@/components/ui/command'
import { Briefcase, Building2, FileText, Activity, UserRound, Settings, LayoutDashboard, Bell, LibraryBig } from 'lucide-react'
import { useRuns, useReports } from '@/hooks/useData'
import { useCompanies } from '@/hooks/useCompanies'
import { useJobs } from '@/hooks/useJobs'

const PAGES = [
  { label: '总览', to: '/', icon: LayoutDashboard },
  { label: '岗位中心', to: '/jobs', icon: Briefcase },
  { label: '企业监控', to: '/companies', icon: Building2 },
  { label: '优质企业候选库', to: '/company-candidates', icon: LibraryBig },
  { label: '运行中心', to: '/runs', icon: Activity },
  { label: '日报中心', to: '/reports', icon: FileText },
  { label: '用户画像', to: '/profile', icon: UserRound },
  { label: '系统设置', to: '/settings', icon: Settings },
  { label: '通知中心', to: '/notifications', icon: Bell },
]

/** 全局搜索弹窗：Ctrl/Cmd + K 唤起 */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const { data: jobs } = useJobs({ tab: 'all' })
  const { data: companies } = useCompanies()
  const { data: reports } = useReports()
  const { data: runs } = useRuns()

  const kw = query.trim().toLowerCase()
  const filteredJobs = useMemo(
    () =>
      kw
        ? (jobs ?? [])
            .filter((j) => [j.title, j.companyName, j.city, ...j.tags].join(' ').toLowerCase().includes(kw))
            .slice(0, 5)
        : (jobs ?? []).slice(0, 3),
    [jobs, kw],
  )
  const filteredCompanies = useMemo(
    () =>
      kw
        ? (companies ?? [])
            .filter((c) => [c.name, c.shortName, c.industry].join(' ').toLowerCase().includes(kw))
            .slice(0, 5)
        : (companies ?? []).slice(0, 3),
    [companies, kw],
  )

  const go = (to: string) => {
    setOpen(false)
    setQuery('')
    navigate(to)
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="搜索岗位、企业、技能关键词、城市、运行记录…" value={query} onValueChange={setQuery} />
      <CommandList>
        <CommandEmpty>
          <div className="py-2">
            <p className="text-[13px] text-ink-secondary">没有找到与「{query}」相关的结果</p>
            {kw && (
              <button
                className="mt-1 text-[13px] text-brand hover:underline"
                onClick={() => go(`/search?q=${encodeURIComponent(query)}`)}
              >
                在全局搜索中查看完整结果
              </button>
            )}
          </div>
        </CommandEmpty>

        <CommandGroup heading="页面">
          {PAGES.map((p) => (
            <CommandItem key={p.to} onSelect={() => go(p.to)}>
              <p.icon className="size-4 text-ink-tertiary" />
              {p.label}
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />
        <CommandGroup heading="岗位">
          {filteredJobs.map((j) => (
            <CommandItem key={j.id} onSelect={() => go(`/jobs/${j.id}`)}>
              <Briefcase className="size-4 text-ink-tertiary" />
              <span className="truncate">{j.title}</span>
              <span className="ml-2 text-[12px] text-ink-tertiary truncate">{j.companyName}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandGroup heading="企业">
          {filteredCompanies.map((c) => (
            <CommandItem key={c.id} onSelect={() => go(`/companies/${c.id}`)}>
              <Building2 className="size-4 text-ink-tertiary" />
              {c.name}
              <span className="ml-2 text-[12px] text-ink-tertiary">{c.industry}</span>
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandGroup heading="日报与运行记录">
          {(reports ?? []).slice(0, 3).map((r) => (
            <CommandItem key={r.date} onSelect={() => go(`/reports/${r.date}`)}>
              <FileText className="size-4 text-ink-tertiary" />
              {r.date} 日报
            </CommandItem>
          ))}
          {(runs ?? []).slice(0, 3).map((r) => (
            <CommandItem key={r.id} onSelect={() => go(`/runs/${r.id}`)}>
              <Activity className="size-4 text-ink-tertiary" />
              {r.code}
            </CommandItem>
          ))}
        </CommandGroup>

        {kw && (
          <>
            <CommandSeparator />
            <CommandGroup heading="搜索">
              <CommandItem onSelect={() => go(`/search?q=${encodeURIComponent(query)}`)}>
                查看「{query}」的全部搜索结果
                <CommandShortcut>↵</CommandShortcut>
              </CommandItem>
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  )
}
