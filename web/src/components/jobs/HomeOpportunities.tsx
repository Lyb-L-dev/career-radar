import { Link } from 'react-router'
import { useJobs } from '@/hooks/useJobs'
import { usePlatformLeads } from '@/hooks/usePlatformLeads'
import { bossOpportunities, officialOpportunities } from '@/lib/opportunities'
import { formatLocalTime, jobDetailHref } from '@/lib/browserState'
import { Button } from '@/components/ui/button'
import { ListSkeleton } from '@/components/common/StateViews'
import { SourceNote } from './SourceNote'
import { EligibilityBadge } from './OfficialAssessment'

function Reason({ text }: { text: string }) {
  if (!text) return null
  return <details className="mt-2 text-sm text-ink-secondary"><summary className="cursor-pointer leading-6">{text.slice(0, 88)}{text.length > 88 ? '… · 展开全文' : ''}</summary><p className="mt-2 reading-copy text-ink-body">{text}</p></details>
}

export default function HomeOpportunities() {
  const official = useJobs({ tab: 'all' })
  const boss = usePlatformLeads()
  const jobs = officialOpportunities(official.data ?? [])
  const leads = bossOpportunities(boss.data ?? [])
  const latest = boss.data?.map(lead => lead.lastSeenAt).sort().at(-1)
  return <section aria-label="值得核对的岗位" className="grid gap-5 lg:grid-cols-2">
    <section className="min-w-0 rounded-xl bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">企业招聘页机会</h2><Link to="/jobs?source=official" className="text-sm text-brand-foreground hover:underline">查看全部官网岗位 →</Link></div>
      <p className="mt-1 text-xs text-ink-secondary">按已有推荐、资格待核对、待评估的顺序选取</p>
      {official.isError && <p role="status" className="mt-3 text-sm text-danger">{official.data ? '刷新失败，保留上次结果。' : '官网岗位读取失败。'}<Button variant="ghost" onClick={() => void official.refetch()}>重试</Button></p>}
      {official.isPending ? <ListSkeleton rows={3} /> : !jobs.length ? <p className="py-5 text-sm text-ink-secondary">暂无优先候选，可到岗位中心查看完整列表。</p> : <ul className="mt-3 divide-y divide-black/5">{jobs.map(job => <li key={job.id} className="py-4">
        <Link to={jobDetailHref(job.id, '/jobs?source=official')} className="font-semibold text-ink hover:text-brand-foreground">{job.title}</Link>
        <p className="mt-1 text-sm text-ink-secondary">{job.companyName} · {job.city || '地点未提供'}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs"><SourceNote kind="official" site={job.source?.site} /><EligibilityBadge result={job.eligibility} /><span className="text-ink-secondary">更新于 {formatLocalTime(job.lastUpdatedAt)}</span></div>
        <Reason text={job.recommendReason ?? ''} />
        <Link className="mt-2 inline-block min-h-7 text-sm text-brand-foreground hover:underline" to={jobDetailHref(job.id, '/jobs?source=official')}>{job.eligibility?.verdict === 'eligible' ? '阅读 JD 与画像判断' : '核对资格与 JD'} →</Link>
      </li>)}</ul>}
    </section>
    <section className="min-w-0 rounded-xl bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">BOSS 平台线索</h2><Link to="/jobs?source=boss" className="text-sm text-brand-foreground hover:underline">查看全部平台线索 →</Link></div>
      <p className="mt-1 text-xs text-ink-secondary">最近采集 {formatLocalTime(latest)} · 与官网分别判断，不代表全市场</p>
      {boss.isError && <p role="status" className="mt-3 text-sm text-danger">{boss.data ? '刷新失败，保留上次结果。' : '平台线索读取失败。'}<Button variant="ghost" onClick={() => void boss.refetch()}>重试</Button></p>}
      {boss.isPending ? <ListSkeleton rows={3} /> : !leads.length ? <p className="py-5 text-sm text-ink-secondary">暂无优先阅读的线索，可查看完整平台列表。</p> : <ul className="mt-3 divide-y divide-black/5">{leads.map(lead => <li key={lead.id} className="py-4">
        <Link to={`/jobs?source=boss&lead=${encodeURIComponent(lead.id)}`} className="font-semibold text-ink hover:text-brand-foreground">{lead.title}</Link>
        <p className="mt-1 text-sm text-ink-secondary">{lead.company || '招聘方待核对'} · {lead.location || '地点未提供'}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs"><SourceNote kind="boss" /><span>{lead.category === 'priority' ? '优先阅读' : '需要核对'}</span><span className={lead.aiResult?.eligibility === 'eligible' && !lead.aiNeedsRefresh ? 'text-success' : 'text-warning'}>{lead.aiResult?.eligibility === 'eligible' && !lead.aiNeedsRefresh ? 'AI 核对：资格符合' : '资格待核对'}</span><span className="text-ink-secondary">{lead.jdComplete ? '已保存 JD' : 'JD 待确认'}</span></div>
        <Reason text={lead.aiResult?.summary || lead.reasons.join('；')} />
        <Link to={`/jobs?source=boss&lead=${encodeURIComponent(lead.id)}`} className="mt-2 inline-block min-h-7 text-sm text-brand-foreground hover:underline">核对完整 JD 与平台条件 →</Link>
      </li>)}</ul>}
    </section>
  </section>
}
