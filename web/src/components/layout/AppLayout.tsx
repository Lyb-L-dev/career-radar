import { useState } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router'
import { Search, Bell, Menu, CircleCheck, TriangleAlert, ChevronDown, UserRound, Settings, LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from '@/components/ui/sheet'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { SidebarContent } from './Sidebar'
import { CommandPalette } from './CommandPalette'
import { useUnreadCount, useDashboardStats } from '@/hooks/useData'

/** 顶部左侧当前页面名（根据路由推导）。 */
function usePageTitle(): string {
  const { pathname } = useLocation()
  if (pathname === '/') return '总览'
  if (pathname.startsWith('/jobs/')) return '岗位详情'
  if (pathname.startsWith('/jobs')) return '岗位中心'
  if (pathname.startsWith('/companies/')) return '企业详情'
  if (pathname.startsWith('/companies')) return '企业监控'
  if (pathname.startsWith('/runs/')) return '运行详情'
  if (pathname.startsWith('/runs')) return '运行中心'
  if (pathname.startsWith('/reports/')) return '日报详情'
  if (pathname.startsWith('/reports')) return '日报中心'
  if (pathname.startsWith('/profile')) return '用户画像'
  if (pathname.startsWith('/settings')) return '系统设置'
  if (pathname.startsWith('/notifications')) return '通知中心'
  if (pathname.startsWith('/search')) return '全局搜索'
  return 'Career Radar'
}

function LastRunStatus() {
  const { data } = useDashboardStats()
  if (!data) return null
  const failed = data.attentionItems.some((i) => i.kind === 'company_failed')
  return (
    <Link
      to="/runs"
      className="hidden lg:flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] text-ink-secondary hover:bg-black/[0.04] transition-colors"
      title={`上次扫描完成于 ${data.lastScanAt}`}
    >
      {failed ? (
        <TriangleAlert className="size-3.5 text-warning" />
      ) : (
        <CircleCheck className="size-3.5 text-success" />
      )}
      上次扫描 {data.lastScanAt.slice(5, 16)}
    </Link>
  )
}

function NotificationBell() {
  const { data: unread } = useUnreadCount()
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate('/notifications')}
      className="relative flex size-9 items-center justify-center rounded-lg text-ink-secondary hover:bg-black/[0.04] hover:text-ink transition-colors"
      aria-label="通知中心"
    >
      <Bell className="size-[18px]" />
      {unread ? (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-medium text-white">
          {unread}
        </span>
      ) : null}
    </button>
  )
}

function UserMenu() {
  const navigate = useNavigate()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-black/[0.04] transition-colors">
          <Avatar className="size-8">
            <AvatarFallback className="bg-brand-soft text-brand-foreground text-[13px] font-medium">26</AvatarFallback>
          </Avatar>
          <span className="hidden md:block text-[13px] text-ink-body">2026 届求职者</span>
          <ChevronDown className="hidden md:block size-3.5 text-ink-tertiary" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onClick={() => navigate('/profile')}>
          <UserRound className="size-4" />
          用户画像
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/settings')}>
          <Settings className="size-4" />
          系统设置
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/onboarding')}>
          <LogOut className="size-4" />
          重新配置
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default function AppLayout() {
  const title = usePageTitle()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="min-h-screen bg-background">
      {/* 桌面侧边栏 */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 border-r border-black/[0.05] bg-sidebar-background md:block">
        <SidebarContent />
      </aside>

      <div className="md:pl-56">
        {/* 顶部操作栏 */}
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-black/[0.05] bg-background/80 backdrop-blur px-4 md:px-8">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="md:hidden" aria-label="打开导航">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SheetTitle className="sr-only">导航菜单</SheetTitle>
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          <h1 className="text-[17px] font-semibold text-ink">{title}</h1>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))}
              className="flex items-center gap-2 rounded-lg border border-black/[0.08] bg-surface px-3 py-1.5 text-[13px] text-ink-tertiary hover:border-black/[0.16] transition-colors"
            >
              <Search className="size-4" />
              <span className="hidden sm:inline">搜索岗位、企业、运行记录</span>
              <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-black/[0.08] bg-black/[0.03] px-1.5 text-[11px]">
                ⌘K
              </kbd>
            </button>
            <LastRunStatus />
            <NotificationBell />
            <UserMenu />
          </div>
        </header>

        {/* 主内容区 */}
        <main className="mx-auto w-full max-w-[1440px] px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>

      <CommandPalette />
    </div>
  )
}
