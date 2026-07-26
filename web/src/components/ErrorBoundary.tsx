import { Component, type ReactNode, type ErrorInfo } from 'react'
import { Button } from '@/components/ui/button'
import { Radar, RotateCcw, Home } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

/** 全局错误边界：页面渲染异常时给出可理解的错误页 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[CareerRadar] 页面渲染异常：', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background px-6 text-center">
        <span className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-brand text-white">
          <Radar className="size-7" />
        </span>
        <h1 className="text-[24px] font-semibold text-ink">页面出现了一些问题</h1>
        <p className="mt-2 max-w-md text-[14px] text-ink-secondary">
          当前页面渲染时发生异常，你的数据（岗位、企业、设置）不受影响。可以尝试刷新页面，或返回总览继续使用。
        </p>
        <div className="mt-6 flex items-center gap-3">
          <Button onClick={() => window.location.reload()}>
            <RotateCcw className="size-4" />
            刷新页面
          </Button>
          <Button variant="outline" onClick={() => (window.location.href = '/')}>
            <Home className="size-4" />
            返回总览
          </Button>
        </div>
        <details className="mt-8 max-w-lg text-left">
          <summary className="cursor-pointer text-[13px] text-ink-tertiary hover:text-ink">查看技术详情</summary>
          <pre className="mt-2 overflow-auto rounded-lg bg-black/[0.04] p-4 text-[12px] text-ink-secondary">
            {this.state.message || '未知错误'}
          </pre>
        </details>
      </div>
    )
  }
}
