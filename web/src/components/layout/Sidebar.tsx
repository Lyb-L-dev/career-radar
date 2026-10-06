import { NavLink } from 'react-router'
import {
  LayoutDashboard,
  Briefcase,
  Building2,
  Activity,
  FileText,
  Radar,
  FileUser,
  Map,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: '总览', icon: LayoutDashboard, end: true },
  { to: '/growth', label: '成长计划', icon: Map },
  { to: '/jobs', label: '岗位', icon: Briefcase },
  { to: '/applications', label: '申请材料', icon: FileUser },
  { to: '/companies', label: '企业监控', icon: Building2 },
  { to: '/runs', label: '运行', icon: Activity },
  { to: '/reports', label: '日报', icon: FileText },
] as const

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      {/* 品牌区 */}
      <div className="flex h-16 items-center gap-2.5 px-5 shrink-0">
        <span className="flex size-8 items-center justify-center rounded-lg bg-brand-mark text-white">
          <Radar className="size-4" />
        </span>
        <div className="leading-tight">
          <p className="text-[15px] font-semibold text-ink">Career Radar</p>
          <p className="text-[11px] text-ink-tertiary">本地求职工作台</p>
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex-1 px-3 py-2 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={'end' in item ? item.end : false}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition-colors',
                isActive
                  ? 'bg-brand-soft text-brand-foreground font-medium'
                  : 'text-ink-body hover:bg-black/[0.04]',
              )
            }
          >
            <item.icon className="size-[18px] shrink-0" />
            {item.label}
          </NavLink>
        ))}
      </nav>

    </div>
  )
}
