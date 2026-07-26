import { cn } from '@/lib/utils'
import type { MatchLevel, JobStatus, CompanyStatus, RunStatus, EmailStatus } from '@/types'
import { MATCH_LEVEL_LABEL, JOB_STATUS_LABEL, COMPANY_STATUS_LABEL, RUN_STATUS_LABEL } from '@/types'

const base = 'inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[12px] font-medium leading-5 whitespace-nowrap'

const palettes = {
  blue: 'bg-brand-soft text-brand-foreground',
  green: 'bg-success-soft text-success',
  amber: 'bg-warning-soft text-warning',
  red: 'bg-danger-soft text-danger',
  gray: 'bg-black/[0.05] text-ink-secondary',
  orange: 'bg-highlight-soft text-highlight',
} as const

export function Pill({ tone, children, className }: { tone: keyof typeof palettes; children: React.ReactNode; className?: string }) {
  return <span className={cn(base, palettes[tone], className)}>{children}</span>
}

export function MatchBadge({ level }: { level: MatchLevel }) {
  const tone = level === 'high' ? 'green' : level === 'medium' ? 'blue' : level === 'low' ? 'gray' : 'gray'
  return <Pill tone={tone}>{MATCH_LEVEL_LABEL[level]}</Pill>
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, { tone: keyof typeof palettes }> = {
    new: { tone: 'green' },
    updated: { tone: 'blue' },
    closed: { tone: 'gray' },
    ignored: { tone: 'gray' },
  }
  return <Pill tone={map[status].tone}>{JOB_STATUS_LABEL[status]}</Pill>
}

export function CompanyStatusBadge({ status }: { status: CompanyStatus }) {
  const map: Record<CompanyStatus, keyof typeof palettes> = {
    active: 'green',
    scanning: 'blue',
    pending_verification: 'amber',
    robots_blocked: 'red',
    structure_error: 'red',
    request_failed: 'red',
    paused: 'gray',
  }
  return (
    <Pill tone={map[status]}>
      {status === 'active' && <span className="size-1.5 rounded-full bg-success" />}
      {status === 'scanning' && <span className="size-1.5 rounded-full bg-brand animate-pulse" />}
      {COMPANY_STATUS_LABEL[status]}
    </Pill>
  )
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, keyof typeof palettes> = {
    pending: 'gray',
    running: 'blue',
    stopping: 'amber',
    completed: 'green',
    partial: 'amber',
    interrupted: 'gray',
    failed: 'red',
  }
  return <Pill tone={map[status]}>{RUN_STATUS_LABEL[status]}</Pill>
}

export function EmailStatusBadge({ status }: { status: EmailStatus }) {
  const map: Record<EmailStatus, { label: string; tone: keyof typeof palettes }> = {
    sent: { label: '已发送', tone: 'green' },
    not_sent: { label: '未发送', tone: 'gray' },
    failed: { label: '发送失败', tone: 'red' },
    disabled: { label: '未启用', tone: 'gray' },
  }
  return <Pill tone={map[status].tone}>{map[status].label}</Pill>
}

/** 岗位难度：x/10 + 小刻度条 */
export function DifficultyMeter({ value, className }: { value: number; className?: string }) {
  const v = Math.max(0, Math.min(10, value))
  const color = v <= 3 ? 'bg-success' : v <= 6 ? 'bg-warning' : 'bg-danger'
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className="text-[13px] font-medium text-ink tabular-nums">{v}/10</span>
      <span className="flex gap-[3px]">
        {Array.from({ length: 10 }).map((_, i) => (
          <span key={i} className={cn('h-1.5 w-[3px] rounded-full', i < v ? color : 'bg-black/10')} />
        ))}
      </span>
    </span>
  )
}
