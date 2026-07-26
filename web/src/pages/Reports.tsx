import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { FileText, FilePlus2, Download, Mail, FileSpreadsheet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { PageHeader, Card } from '@/components/common/PageHeader'
import { EmailStatusBadge, Pill } from '@/components/common/Badges'
import { ListSkeleton, EmptyState, ErrorState } from '@/components/common/StateViews'
import { useReports } from '@/hooks/useData'
import { downloadReport, resendReportEmail } from '@/services/reports'
import { createRun } from '@/services/runs'

export default function ReportsPage() {
  const navigate = useNavigate()
  const { data: reports, isLoading, isError, refetch } = useReports()
  const [date, setDate] = useState('')
  const [type, setType] = useState('all')
  const [matchedOnly, setMatchedOnly] = useState(false)
  const [generating, setGenerating] = useState(false)

  return (
    <div className="space-y-5">
      <PageHeader
        title="日报中心"
        subtitle="每天扫描结束后生成的求职情报简报"
        actions={
          <Button
            className="bg-brand hover:bg-brand-hover text-white"
            disabled={generating}
            onClick={async () => {
              setGenerating(true)
              try {
                const result = await createRun({ scope: 'all', sendEmail: false })
                toast.success('真实扫描任务已创建', { description: '日报会在扫描完成后生成。' })
                navigate(`/runs/${result.runId}`)
              } catch (error) {
                toast.error('创建扫描任务失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
              } finally {
                setGenerating(false)
              }
            }}
          >
            <FilePlus2 className="size-4" />
            {generating ? '正在创建任务…' : '扫描并生成日报'}
          </Button>
        }
      />

      {/* 筛选 */}
      <Card padded={false} className="flex flex-wrap items-center gap-3 p-4">
        <Input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="h-9 w-44 rounded-lg bg-surface-subtle border-black/[0.06]"
        />
        <Select value={type} onValueChange={setType}>
          <SelectTrigger className="h-9 w-40 rounded-lg"><SelectValue placeholder="报告类型" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            <SelectItem value="daily">每日日报</SelectItem>
            <SelectItem value="manual">手动生成</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Switch id="matched-only" checked={matchedOnly} onCheckedChange={setMatchedOnly} />
          <Label htmlFor="matched-only" className="text-[13px]">只看匹配岗位</Label>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto text-ink-secondary"
          onClick={() => {
            setDate(''); setType('all'); setMatchedOnly(false)
          }}
        >
          重置
        </Button>
      </Card>

      <Card padded={false}>
        {isLoading ? (
          <div className="p-4"><ListSkeleton rows={5} /></div>
        ) : isError ? (
          <ErrorState onRetry={() => refetch()} />
        ) : !reports || reports.length === 0 ? (
          <EmptyState
            icon={<FileText className="size-6" />}
            title="还没有日报"
            description="完成第一次扫描后，系统会在这里生成岗位日报。"
            actions={
              <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => navigate('/')}>
                去总览发起扫描
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>日期</TableHead>
                  <TableHead>新增岗位</TableHead>
                  <TableHead>更新岗位</TableHead>
                  <TableHead>高匹配</TableHead>
                  <TableHead>Markdown</TableHead>
                  <TableHead>CSV</TableHead>
                  <TableHead>邮件</TableHead>
                  <TableHead className="text-right pr-4">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((r) => (
                  <TableRow key={r.date}>
                    <TableCell>
                      <button onClick={() => navigate(`/reports/${r.date}`)} className="font-medium text-brand hover:underline tabular-nums">
                        {r.date}
                      </button>
                    </TableCell>
                    <TableCell className="tabular-nums text-[13px]">{r.newJobs}</TableCell>
                    <TableCell className="tabular-nums text-[13px]">{r.updatedJobs}</TableCell>
                    <TableCell>
                      {r.highMatchJobs > 0 ? <Pill tone="orange">{r.highMatchJobs}</Pill> : <span className="text-[13px] text-ink-tertiary">0</span>}
                    </TableCell>
                    <TableCell>
                      {r.markdownStatus === 'generated' ? <Pill tone="green">已生成</Pill> : <Pill tone="gray">未生成</Pill>}
                    </TableCell>
                    <TableCell>
                      {r.csvStatus === 'generated' ? <Pill tone="green">已生成</Pill> : <Pill tone="gray">未生成</Pill>}
                    </TableCell>
                    <TableCell><EmailStatusBadge status={r.emailStatus} /></TableCell>
                    <TableCell className="pr-4">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" className="text-brand" onClick={() => navigate(`/reports/${r.date}`)}>
                          查看日报
                        </Button>
                        <Button
                          variant="ghost" size="icon" className="size-8 text-ink-tertiary" aria-label="下载 Markdown"
                          onClick={async () => {
                            try { await downloadReport(r.date, 'md'); toast.success('Markdown 日报已下载') }
                            catch (error) { toast.error('下载失败', { description: error instanceof Error ? error.message : '文件不存在。' }) }
                          }}
                        >
                          <Download className="size-4" />
                        </Button>
                        <Button
                          variant="ghost" size="icon" className="size-8 text-ink-tertiary" aria-label="下载 CSV"
                          onClick={async () => {
                            try { await downloadReport(r.date, 'csv'); toast.success('CSV 日报已下载') }
                            catch (error) { toast.error('下载失败', { description: error instanceof Error ? error.message : '文件不存在。' }) }
                          }}
                        >
                          <FileSpreadsheet className="size-4" />
                        </Button>
                        <Button
                          variant="ghost" size="icon" className="size-8 text-ink-tertiary" aria-label="重新发送邮件"
                          onClick={async () => {
                            try {
                              const res = await resendReportEmail(r.date)
                              if (res.ok) toast.success('邮件已重新发送')
                            } catch (error) {
                              toast.error('邮件发送失败', { description: error instanceof Error ? error.message : '请检查 SMTP 配置。' })
                            }
                          }}
                        >
                          <Mail className="size-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </div>
  )
}
