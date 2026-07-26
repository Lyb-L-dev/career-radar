import { Link, useNavigate } from 'react-router'
import { Radar, Home, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-6 text-center">
      <span className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-brand text-white">
        <Radar className="size-7" />
      </span>
      <p className="text-[64px] font-semibold leading-none text-ink/10">404</p>
      <h1 className="mt-2 text-[22px] font-semibold text-ink">页面不存在</h1>
      <p className="mt-2 max-w-sm text-[14px] text-ink-secondary">
        你要找的页面可能已被移动或删除。可以返回总览，继续查看今天的新岗位。
      </p>
      <div className="mt-6 flex items-center gap-3">
        <Button variant="outline" onClick={() => navigate(-1)}>
          <ArrowLeft className="size-4" />
          返回上一页
        </Button>
        <Link to="/">
          <Button className="bg-brand hover:bg-brand-hover text-white">
            <Home className="size-4" />
            回到总览
          </Button>
        </Link>
      </div>
    </div>
  )
}
