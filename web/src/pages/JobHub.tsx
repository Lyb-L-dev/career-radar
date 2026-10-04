import { useSearchParams } from 'react-router'
import { BriefcaseBusiness, Compass } from 'lucide-react'
import { Button } from '@/components/ui/button'
import OfficialJobsPage from './Jobs'
import PlatformLeadsPage from './PlatformLeads'
import UnifiedJobsPage from './UnifiedJobs'

export default function JobHubPage() {
  const [params, setParams] = useSearchParams()
  const sourceParam = params.get('source')
  const source = sourceParam === 'boss' ? 'boss' : sourceParam === 'official' || params.has('tab') ? 'official' : 'all'

  const switchSource = (next: 'all' | 'official' | 'boss') => {
    const updated = next === 'all' ? new URLSearchParams() : new URLSearchParams(params)
    updated.delete('lead')
    if (next !== 'all') {
      updated.set('source', next)
      if (next === 'boss') updated.delete('tab')
    }
    setParams(updated)
  }

  return (
    <div className="space-y-5">
      <div className="flex gap-1 rounded-lg border border-black/[0.08] bg-surface p-1 w-fit" role="group" aria-label="岗位来源">
          <Button size="sm" variant={source === 'all' ? 'secondary' : 'ghost'} aria-pressed={source === 'all'} onClick={() => switchSource('all')}>全部来源</Button>
          <Button size="sm" variant={source === 'official' ? 'secondary' : 'ghost'} aria-pressed={source === 'official'} onClick={() => switchSource('official')}>
            <BriefcaseBusiness className="size-4" />企业招聘页
          </Button>
          <Button size="sm" variant={source === 'boss' ? 'secondary' : 'ghost'} aria-pressed={source === 'boss'} onClick={() => switchSource('boss')}>
            <Compass className="size-4" />BOSS直聘
          </Button>
      </div>
      {source === 'all' ? <UnifiedJobsPage /> : source === 'boss' ? <PlatformLeadsPage embedded focusLeadId={params.get('lead')} /> : <OfficialJobsPage embedded />}
    </div>
  )
}
