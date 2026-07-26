import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Inbox, AlertCircle, SearchX } from 'lucide-react'

/** 列表加载骨架 */
export function ListSkeleton({ rows = 5, card }: { rows?: number; card?: boolean }) {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="加载中">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={card ? 'rounded-xl bg-surface p-5 shadow-card' : 'rounded-lg bg-surface p-4 shadow-card'}>
          <div className="flex items-center gap-4">
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-16 ml-auto" />
          </div>
          <Skeleton className="mt-3 h-4 w-2/3" />
        </div>
      ))}
    </div>
  )
}

/** 页面级加载骨架（标题 + 卡片网格） */
export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-5 w-96" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 rounded-xl" />
    </div>
  )
}

/** 空状态：差异化文案 + 操作按钮 */
export function EmptyState({
  icon,
  title,
  description,
  actions,
}: {
  icon?: ReactNode
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-black/[0.04] text-ink-tertiary">
        {icon ?? <Inbox className="size-6" />}
      </div>
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {description ? <p className="mt-1.5 max-w-md text-[13px] text-ink-secondary">{description}</p> : null}
      {actions ? <div className="mt-5 flex flex-wrap items-center justify-center gap-3">{actions}</div> : null}
    </div>
  )
}

/** 搜索无结果 */
export function NoResults({ onClear }: { onClear?: () => void }) {
  return (
    <EmptyState
      icon={<SearchX className="size-6" />}
      title="没有找到匹配的结果"
      description="换个关键词试试，或清除筛选条件后重新查看。"
      actions={onClear ? <Button variant="outline" onClick={onClear}>清除筛选条件</Button> : undefined}
    />
  )
}

/** 错误状态：可理解原因 + 重试 */
export function ErrorState({
  title = '数据加载失败',
  description = '网络或服务暂时不可用，请稍后重试。当前页面其他内容不受影响。',
  onRetry,
}: {
  title?: string
  description?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
      <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-danger-soft text-danger">
        <AlertCircle className="size-6" />
      </div>
      <p className="text-[15px] font-medium text-ink">{title}</p>
      <p className="mt-1.5 max-w-md text-[13px] text-ink-secondary">{description}</p>
      {onRetry ? (
        <Button variant="outline" className="mt-5" onClick={onRetry}>
          重新加载
        </Button>
      ) : null}
    </div>
  )
}
