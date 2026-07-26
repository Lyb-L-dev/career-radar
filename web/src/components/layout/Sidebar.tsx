import { NavLink } from 'react-router'
import {
  LayoutDashboard,
  Briefcase,
  Building2,
  LibraryBig,
  Activity,
  FileText,
  UserRound,
  Settings,
  Github,
  Radar,
  CircleCheck,
  FileUser,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: '总览', icon: LayoutDashboard, end: true },
  { to: '/jobs', label: '岗位中心', icon: Briefcase },
  { to: '/applications', label: 'AI 申请材料', icon: FileUser },
  { to: '/companies', label: '企业监控', icon: Building2 },
  { to: '/company-candidates', label: '优质企业候选库', icon: LibraryBig },
  { to: '/runs', label: '运行中心', icon: Activity },
  { to: '/reports', label: '日报中心', icon: FileText },
  { to: '/profile', label: '用户画像', icon: UserRound },
  { to: '/settings', label: '系统设置', icon: Settings },
] as const

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      {/* 品牌区 */}
      <div className="flex h-16 items-center gap-2.5 px-5 shrink-0">
        <span className="flex size-8 items-center justify-center rounded-lg bg-brand text-white">
          <Radar className="size-4" />
        </span>
        <div className="leading-tight">
          <p className="text-[15px] font-semibold text-ink">Career Radar</p>
          <p className="text-[11px] text-ink-tertiary">企业官网职位监控</p>
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

      {/* 底部信息 */}
      <div className="px-5 py-4 space-y-2.5 border-t border-black/[0.05]">
        <div className="flex items-center gap-1.5 text-[12px] text-success">
          <CircleCheck className="size-3.5" />
          服务运行正常
        </div>
        <a
          href="https://github.com/"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 text-[12px] text-ink-secondary hover:text-ink transition-colors"
        >
          <Github className="size-3.5" />
          GitHub 项目
        </a>
        <p className="text-[11px] text-ink-tertiary">Career Radar v1.1.0</p>
      </div>
    </div>
  )
}
