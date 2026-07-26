import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** 页面标题区：主标题 32px + 副标题 + 右侧操作区 */
export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-wrap items-start justify-between gap-4', className)}>
      <div className="min-w-0">
        <h1 className="text-[28px] md:text-[32px] font-semibold text-ink tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1.5 text-[15px] text-ink-secondary">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-3 shrink-0">{actions}</div> : null}
    </div>
  )
}

/** 白色内容卡片（统一 12px 圆角与克制阴影） */
export function Card({
  children,
  className,
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <div className={cn('bg-surface rounded-xl shadow-card', padded && 'p-6', className)}>
      {children}
    </div>
  )
}

/** 卡片内模块标题 20px */
export function CardTitle({ children, extra }: { children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="text-[18px] font-semibold text-ink">{children}</h2>
      {extra}
    </div>
  )
}
