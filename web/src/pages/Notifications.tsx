import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  Bell,
  CheckCheck,
  Trash2,
  Sparkles,
  Building2,
  Activity,
  FileText,
  MailWarning,
  Settings2,
  Info,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { ListSkeleton, EmptyState, ErrorState } from '@/components/common/StateViews'
import { useNotifications, useNotificationActions } from '@/hooks/useData'
import { useState } from 'react'
import type { NotificationItem, NotificationType } from '@/types'
import { cn } from '@/lib/utils'

const TYPE_META: Record<NotificationType, { icon: React.ReactNode; label: string }> = {
  high_match_job: { icon: <Sparkles className="size-4 text-highlight" />, label: '高匹配岗位' },
  company_failed: { icon: <Building2 className="size-4 text-danger" />, label: '企业异常' },
  run_completed: { icon: <Activity className="size-4 text-brand" />, label: '任务完成' },
  report_ready: { icon: <FileText className="size-4 text-success" />, label: '日报就绪' },
  email_failed: { icon: <MailWarning className="size-4 text-warning" />, label: '邮件失败' },
  config_error: { icon: <Settings2 className="size-4 text-warning" />, label: '配置提醒' },
  system: { icon: <Info className="size-4 text-ink-tertiary" />, label: '系统提示' },
}

function NotificationRow({ n }: { n: NotificationItem }) {
  const navigate = useNavigate()
  const { markRead, remove } = useNotificationActions()
  const meta = TYPE_META[n.type]
  return (
    <li
      className={cn(
        'group flex items-start gap-3.5 px-5 py-4 transition-colors hover:bg-black/[0.02]',
        !n.read && 'bg-brand-soft/40',
      )}
    >
      <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface shadow-card">
        {meta.icon}
      </span>
      <button
        className="min-w-0 flex-1 text-left"
        onClick={() => {
          if (!n.read) markRead.mutate(n.id)
          if (n.link) navigate(n.link)
        }}
      >
        <p className={cn('text-[14px] text-ink', !n.read && 'font-medium')}>
          {!n.read && <span className="mr-1.5 inline-block size-1.5 rounded-full bg-brand align-middle" />}
          {n.title}
        </p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-secondary">{n.body}</p>
        <p className="mt-1 text-[12px] text-ink-tertiary">
          {meta.label} · {n.time}
        </p>
      </button>
      <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
        {!n.read && (
          <Button
            variant="ghost"
            size="sm"
            className="text-[12px] text-ink-secondary"
            onClick={() => {
              markRead.mutate(n.id)
              toast.success('已标记为已读')
            }}
          >
            标记已读
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="size-8 text-ink-tertiary hover:text-danger"
          aria-label="删除通知"
          onClick={() => {
            remove.mutate(n.id)
            toast.success('通知已删除')
          }}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
    </li>
  )
}

export default function NotificationsPage() {
  const { data: notifications, isLoading, isError, refetch } = useNotifications()
  const { markAll } = useNotificationActions()
  const [tab, setTab] = useState<'all' | 'unread'>('all')

  const list = (notifications ?? []).filter((n) => (tab === 'unread' ? !n.read : true))
  const unreadCount = (notifications ?? []).filter((n) => !n.read).length

  return (
    <div className="space-y-5">
      <PageHeader
        title="通知中心"
        subtitle={unreadCount > 0 ? `${unreadCount} 条未读通知` : '所有通知都已读完'}
        actions={
          <Button
            variant="outline"
            disabled={unreadCount === 0}
            onClick={() => {
              markAll.mutate()
              toast.success('全部通知已标记为已读')
            }}
          >
            <CheckCheck className="size-4" />
            全部已读
          </Button>
        }
      />

      <Tabs value={tab} onValueChange={(v) => setTab(v as 'all' | 'unread')}>
        <TabsList className="bg-surface shadow-card h-10 rounded-lg p-1">
          <TabsTrigger value="all" className="rounded-md px-4">全部</TabsTrigger>
          <TabsTrigger value="unread" className="rounded-md px-4">
            未读{unreadCount > 0 ? `（${unreadCount}）` : ''}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <Card padded={false}>
        {isLoading ? (
          <div className="p-4"><ListSkeleton rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : list.length === 0 ? (
          <EmptyState
            icon={<Bell className="size-6" />}
            title={tab === 'unread' ? '没有未读通知' : '暂无通知'}
            description={tab === 'unread' ? '所有通知都已读完。' : '系统运行中的重要事件会出现在这里。'}
          />
        ) : (
          <ul className="divide-y divide-black/[0.05]">
            {list.map((n) => (
              <NotificationRow key={n.id} n={n} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
