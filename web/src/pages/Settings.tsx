import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import {
  PlugZap,
  Save,
  Send,
  Loader2,
  Database,
  Download,
  Trash2,
  RefreshCw,
  FolderCog,
  ShieldCheck,
  Info,
  CalendarClock,
  Archive,
  BadgeCheck,
  CircleAlert,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { PageHeader, Card, CardTitle } from '@/components/common/PageHeader'
import { Pill } from '@/components/common/Badges'
import { PageSkeleton, ErrorState } from '@/components/common/StateViews'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { useSettings, useSaveSettings } from '@/hooks/useData'
import {
  testLlmConnection,
  sendTestEmail,
  sendTestApprise,
  runMaintenance,
  getDbStats,
  getAutomationStatus,
  changeAutomation,
  getBackups,
  verifyBackup,
  deleteBackup,
} from '@/services/settings'
import type { BackupItem } from '@/services/settings'
import type { AppSettings, RenderMode, MatchLevel } from '@/types'
import { MATCH_LEVEL_LABEL } from '@/types'
import { useQuery, useQueryClient } from '@tanstack/react-query'

function formatBackupSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`
}

function formatBackupTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN')
}

function BackupStatus({ status }: { status: BackupItem['integrityStatus'] }) {
  if (status === 'valid') return <Pill tone="green">校验通过</Pill>
  if (status === 'invalid') return <Pill tone="red">需要处理</Pill>
  return <Pill tone="gray">尚未校验</Pill>
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-[12px] text-ink-tertiary">{hint}</p>}
    </div>
  )
}

function SaveBar({ saving, onSave }: { saving: boolean; onSave: () => void }) {
  return (
    <div className="flex justify-end pt-2">
      <Button className="bg-brand hover:bg-brand-hover text-white" onClick={onSave} disabled={saving}>
        {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
        {saving ? '保存中…' : '保存设置'}
      </Button>
    </div>
  )
}

export default function SettingsPage() {
  const [params] = useSearchParams()
  const tabParam = params.get('tab')
  const { data: settings, isLoading, isError, refetch } = useSettings()

  if (isLoading) return <PageSkeleton />
  if (isError || !settings) return <ErrorState onRetry={() => refetch()} />

  const initialTab = ['basic', 'crawler', 'llm', 'email', 'automation', 'data'].includes(tabParam ?? '')
    ? tabParam!
    : 'basic'
  return <SettingsEditor key={JSON.stringify(settings)} settings={settings} initialTab={initialTab} />
}

function SettingsEditor({ settings, initialTab }: { settings: AppSettings; initialTab: string }) {
  const saveSettings = useSaveSettings()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<AppSettings>(settings)
  const [tab, setTab] = useState(initialTab)
const [llmTesting, setLlmTesting] = useState(false)
const [llmConfirmOpen, setLlmConfirmOpen] = useState(false)
const [emailTesting, setEmailTesting] = useState(false)
const [appriseTesting, setAppriseTesting] = useState(false)
const [automationAction, setAutomationAction] = useState<null | 'install' | 'remove'>(null)
  const [dangerAction, setDangerAction] = useState<null | { key: 'export' | 'clearLogs' | 'rebuildIndex' | 'cleanReports'; title: string; desc: string }>(null)
  const [backupToDelete, setBackupToDelete] = useState<string | null>(null)
  const [verifyingBackup, setVerifyingBackup] = useState<string | null>(null)
  const [deletingBackup, setDeletingBackup] = useState(false)
  const { data: dbStats } = useQuery({ queryKey: ['db-stats'], queryFn: getDbStats })
  const {
    data: backups = [],
    isLoading: backupsLoading,
    isError: backupsError,
    refetch: refetchBackups,
  } = useQuery({ queryKey: ['backups'], queryFn: getBackups })
  const { data: automation, refetch: refetchAutomation } = useQuery({
    queryKey: ['automation-status'],
    queryFn: getAutomationStatus,
  })

  const patch = (fn: (s: AppSettings) => AppSettings) => setDraft(fn(draft))
  const save = (section: string) => {
    saveSettings.mutate(draft, {
      onSuccess: () => toast.success(`${section}已保存`),
      onError: (error) => toast.error(`${section}保存失败`, { description: error.message }),
    })
  }

  return (
    <div className="space-y-5">
      <PageHeader title="系统设置" subtitle="扫描、抓取、LLM 与通知的全局配置" />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-surface shadow-card h-11 rounded-lg p-1">
          <TabsTrigger value="basic" className="rounded-md px-4">基础设置</TabsTrigger>
          <TabsTrigger value="crawler" className="rounded-md px-4">抓取设置</TabsTrigger>
          <TabsTrigger value="llm" className="rounded-md px-4">LLM 设置</TabsTrigger>
          <TabsTrigger value="email" className="rounded-md px-4">邮件通知</TabsTrigger>
          <TabsTrigger value="automation" className="rounded-md px-4">自动化中心</TabsTrigger>
          <TabsTrigger value="data" className="rounded-md px-4">数据与维护</TabsTrigger>
        </TabsList>

        {/* 基础设置 */}
        <TabsContent value="basic" className="mt-5">
          <Card className="max-w-3xl space-y-5">
            <CardTitle>基础设置</CardTitle>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="系统时区">
                <Select value={draft.basic.timezone} onValueChange={(v) => patch((s) => ({ ...s, basic: { ...s.basic, timezone: v } }))}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Asia/Shanghai">Asia/Shanghai (UTC+8)</SelectItem>
                    <SelectItem value="Asia/Tokyo">Asia/Tokyo (UTC+9)</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="每日运行时间" hint="每天自动扫描的开始时间">
                <Input
                  type="time"
                  value={draft.basic.dailyRunTime}
                  onChange={(e) => patch((s) => ({ ...s, basic: { ...s.basic, dailyRunTime: e.target.value } }))}
                  className="rounded-lg"
                />
              </Field>
              <Field label="输出目录" hint="仅允许项目目录内的相对路径，例如 output">
                <Input
                  value={draft.basic.outputDir}
                  onChange={(e) => patch((s) => ({ ...s, basic: { ...s.basic, outputDir: e.target.value } }))}
                  className="rounded-lg font-mono text-[13px]"
                />
              </Field>
              <Field label="数据库位置" hint="仅允许项目目录内的相对路径，例如 data/career_radar.db">
                <Input
                  value={draft.basic.dbPath}
                  onChange={(e) => patch((s) => ({ ...s, basic: { ...s.basic, dbPath: e.target.value } }))}
                  className="rounded-lg font-mono text-[13px]"
                />
              </Field>
              <Field label="日报保留天数" hint="每次扫描完成后自动清理过期日报，也可在数据维护页手动执行。">
                <Input
                  type="number"
                  min={7}
                  max={3650}
                  value={draft.basic.reportRetentionDays}
                  onChange={(e) => patch((s) => ({ ...s, basic: { ...s.basic, reportRetentionDays: Number(e.target.value) } }))}
                  className="rounded-lg"
                />
              </Field>
            </div>
            <SaveBar saving={saveSettings.isPending} onSave={() => save('基础设置')} />
          </Card>
        </TabsContent>

        {/* 抓取设置 */}
        <TabsContent value="crawler" className="mt-5">
          <Card className="max-w-3xl space-y-5">
            <CardTitle>抓取设置</CardTitle>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="同域最小延迟（秒）" hint="同一域名两次请求之间的最小间隔">
                <Input type="number" min={1} value={draft.crawler.minDelay} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, minDelay: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="同域最大延迟（秒）">
                <Input type="number" min={1} value={draft.crawler.maxDelay} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, maxDelay: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="默认渲染模式" hint="自动模式下，静态抓取内容不足时回退浏览器渲染">
                <Select value={draft.crawler.defaultRenderMode} onValueChange={(v) => patch((s) => ({ ...s, crawler: { ...s.crawler, defaultRenderMode: v as RenderMode } }))}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">自动</SelectItem>
                    <SelectItem value="static">静态抓取</SelectItem>
                    <SelectItem value="dynamic">浏览器渲染</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="页面正文最低长度（字符）" hint="低于该长度视为拦截页或加载失败">
                <Input type="number" min={100} value={draft.crawler.minContentLength} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, minContentLength: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="单家公司最大页面数">
                <Input type="number" min={1} max={100} value={draft.crawler.maxPagesPerCompany} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, maxPagesPerCompany: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="单次 LLM 页面上限" hint="只统计新页面或正文发生变化的页面；缓存命中不计入">
                <Input type="number" min={1} max={5000} value={draft.crawler.maxLlmPagesPerRun} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, maxLlmPagesPerRun: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="请求超时（秒）">
                <Input type="number" min={5} max={120} value={draft.crawler.requestTimeout} onChange={(e) => patch((s) => ({ ...s, crawler: { ...s.crawler, requestTimeout: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
            </div>
            <div className="flex items-start justify-between gap-4 rounded-lg bg-surface-subtle px-4 py-3.5">
              <div className="flex gap-2.5">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
                <div>
                  <p className="text-[14px] font-medium text-ink">遵循 robots.txt</p>
                  <p className="mt-0.5 text-[12px] text-ink-secondary">
                    合规抓取的底线策略，默认开启且不允许关闭。被 robots 禁止的站点会自动跳过。
                  </p>
                </div>
              </div>
              <Switch checked={draft.crawler.respectRobots} disabled aria-label="遵循 robots.txt（始终开启）" />
            </div>
            <SaveBar saving={saveSettings.isPending} onSave={() => save('抓取设置')} />
          </Card>
        </TabsContent>

        {/* LLM 设置 */}
        <TabsContent value="llm" className="mt-5">
          <Card className="max-w-3xl space-y-5">
            <CardTitle>LLM 设置</CardTitle>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="服务商" hint="由本机配置决定，API Key 只从环境变量读取。">
                <div className="flex min-h-10 items-center justify-between rounded-lg border border-line bg-surface-subtle px-3">
                  <span className="text-[14px] font-medium text-ink">{draft.llm.provider}</span>
                  <Pill tone="green">当前服务</Pill>
                </div>
              </Field>
              <Field label="模型名称">
                <Input value={draft.llm.model} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, model: e.target.value } }))} className="rounded-lg" />
              </Field>
              <Field label="API Base URL">
                <Input value={draft.llm.apiBaseUrl} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, apiBaseUrl: e.target.value } }))} className="rounded-lg font-mono text-[13px]" />
              </Field>
              <Field label="API Key" hint="出于安全考虑，前端只显示掩码，完整 Key 永不返回">
                <div className="flex items-center gap-2">
                  <Input value={draft.llm.apiKeyMasked} readOnly className="rounded-lg font-mono text-[13px] bg-surface-subtle" />
                  {draft.llm.apiKeyConfigured ? <Pill tone="green">已配置</Pill> : <Pill tone="red">未配置</Pill>}
                </div>
              </Field>
              <Field label="最大切片长度（字符）">
                <Input type="number" value={draft.llm.maxChunkLength} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, maxChunkLength: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="切片重叠长度（字符）">
                <Input type="number" value={draft.llm.chunkOverlap} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, chunkOverlap: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="超时时间（秒）">
                <Input type="number" value={draft.llm.timeout} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, timeout: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
              <Field label="重试次数">
                <Input type="number" min={0} max={5} value={draft.llm.retries} onChange={(e) => patch((s) => ({ ...s, llm: { ...s.llm, retries: Number(e.target.value) } }))} className="rounded-lg" />
              </Field>
            </div>
            <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
              <div>
                <p className="text-[14px] font-medium text-ink">JSON Output</p>
                <p className="text-[12px] text-ink-tertiary">要求模型以 JSON 结构返回岗位字段</p>
              </div>
              <Switch checked={draft.llm.jsonOutput} onCheckedChange={(v) => patch((s) => ({ ...s, llm: { ...s.llm, jsonOutput: v } }))} />
            </div>
            <div className="flex justify-end gap-2.5 pt-2">
              <Button
                variant="outline"
                disabled={llmTesting}
                onClick={() => setLlmConfirmOpen(true)}
              >
                {llmTesting ? <Loader2 className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                {llmTesting ? '正在测试…' : '测试连接'}
              </Button>
              <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => save('LLM 设置')} disabled={saveSettings.isPending}>
                <Save className="size-4" />
                保存设置
              </Button>
            </div>
          </Card>
        </TabsContent>

        {/* 邮件通知 */}
        <TabsContent value="email" className="mt-5">
          <div className="max-w-3xl space-y-4">
            {!draft.email.enabled && (
              <div className="flex items-start gap-2.5 rounded-xl bg-warning-soft px-4 py-3.5 text-[13px] text-warning">
                <Info className="mt-0.5 size-4 shrink-0" />
                邮件通知当前未启用，Markdown 和 CSV 日报仍会正常生成。配置 SMTP 后即可开启每日岗位提醒。
              </div>
            )}
            <Card className="space-y-5">
              <CardTitle>邮件通知</CardTitle>
              <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                <div>
                  <p className="text-[14px] font-medium text-ink">启用邮件提醒</p>
                  <p className="text-[12px] text-ink-tertiary">每日扫描结束后发送岗位摘要</p>
                </div>
                <Switch checked={draft.email.enabled} onCheckedChange={(v) => patch((s) => ({ ...s, email: { ...s.email, enabled: v } }))} />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="SMTP 主机">
                  <Input value={draft.email.smtpHost} onChange={(e) => patch((s) => ({ ...s, email: { ...s.email, smtpHost: e.target.value } }))} placeholder="smtp.example.com" className="rounded-lg" />
                </Field>
                <Field label="端口">
                  <Input type="number" value={draft.email.smtpPort} onChange={(e) => patch((s) => ({ ...s, email: { ...s.email, smtpPort: Number(e.target.value) } }))} className="rounded-lg" />
                </Field>
                <Field label="加密方式">
                  <Select value={draft.email.encryption} onValueChange={(v) => patch((s) => ({ ...s, email: { ...s.email, encryption: v as AppSettings['email']['encryption'] } }))}>
                    <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="SSL">SSL</SelectItem>
                      <SelectItem value="STARTTLS">STARTTLS</SelectItem>
                      <SelectItem value="none">不加密</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="发件地址">
                  <Input value={draft.email.fromAddress} onChange={(e) => patch((s) => ({ ...s, email: { ...s.email, fromAddress: e.target.value } }))} placeholder="radar@example.com" className="rounded-lg" />
                </Field>
                <Field label="最低匹配等级" hint="只有达到该匹配等级的岗位才会进入邮件">
                  <Select value={draft.email.minMatchLevel} onValueChange={(v) => patch((s) => ({ ...s, email: { ...s.email, minMatchLevel: v as MatchLevel } }))}>
                    <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(Object.keys(MATCH_LEVEL_LABEL) as MatchLevel[]).filter((m) => m !== 'unknown').map((m) => (
                        <SelectItem key={m} value={m}>{MATCH_LEVEL_LABEL[m]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="最大岗位难度">
                  <Input type="number" min={1} max={10} value={draft.email.maxDifficulty} onChange={(e) => patch((s) => ({ ...s, email: { ...s.email, maxDifficulty: Number(e.target.value) } }))} className="rounded-lg" />
                </Field>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                  <span className="text-[14px] text-ink">发送新增岗位</span>
                  <Switch checked={draft.email.sendOnNew} onCheckedChange={(v) => patch((s) => ({ ...s, email: { ...s.email, sendOnNew: v } }))} />
                </div>
                <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                  <span className="text-[14px] text-ink">发送更新岗位</span>
                  <Switch checked={draft.email.sendOnUpdate} onCheckedChange={(v) => patch((s) => ({ ...s, email: { ...s.email, sendOnUpdate: v } }))} />
                </div>
              </div>
              <div className="flex justify-end gap-2.5 pt-2">
                <Button
                  variant="outline"
                  disabled={emailTesting}
                  onClick={async () => {
                    setEmailTesting(true)
                    try {
                      const res = await sendTestEmail()
                      if (res.ok) toast.success(res.message)
                      else toast.error('发送失败', { description: res.message })
                    } catch (error) {
                      toast.error('发送失败', { description: error instanceof Error ? error.message : '请检查 SMTP 配置。' })
                    } finally {
                      setEmailTesting(false)
                    }
                  }}
                >
                  {emailTesting ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                  {emailTesting ? '正在发送…' : '发送测试邮件'}
                </Button>
                <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => save('邮件通知设置')} disabled={saveSettings.isPending}>
                  <Save className="size-4" />
                  保存设置
                </Button>
              </div>
            </Card>

            <Card className="space-y-4">
              <CardTitle>其他推送渠道（Apprise）</CardTitle>
              <p className="text-[12px] text-ink-tertiary">
                支持 Telegram、企业微信、钉钉、ntfy 等渠道；URL 在 config.yaml 的
                apprise.urls 中填写，保存后重启服务生效。推送筛选条件与邮件一致。
              </p>
              <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                <div>
                  <p className="text-[14px] font-medium text-ink">
                    {draft.apprise.configured
                      ? `已配置 ${draft.apprise.urlCount} 个渠道`
                      : '未配置渠道'}
                  </p>
                  <p className="text-[12px] text-ink-tertiary">
                    {draft.apprise.enabled
                      ? '启用中：扫描后将同时推送岗位摘要'
                      : '当前未启用'}
                  </p>
                </div>
                {draft.apprise.enabled ? <Pill tone="green">启用</Pill> : <Pill tone="gray">关闭</Pill>}
              </div>
              <div className="flex justify-end pt-1">
                <Button
                  variant="outline"
                  disabled={appriseTesting || !draft.apprise.configured}
                  onClick={async () => {
                    setAppriseTesting(true)
                    try {
                      const res = await sendTestApprise()
                      if (res.ok) toast.success(res.message)
                      else toast.error('发送失败', { description: res.message })
                    } catch (error) {
                      toast.error('发送失败', { description: error instanceof Error ? error.message : '未知错误' })
                    } finally {
                      setAppriseTesting(false)
                    }
                  }}
                >
                  {appriseTesting ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                  {appriseTesting ? '正在发送…' : '发送测试推送'}
                </Button>
              </div>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="automation" className="mt-5">
          <Card className="max-w-3xl space-y-5">
            <CardTitle>
              <span className="flex items-center gap-2">
                <CalendarClock className="size-4 text-brand" />
                每日自动扫描
              </span>
            </CardTitle>
            <div className="flex items-start justify-between gap-4 rounded-xl bg-surface-subtle p-4">
              <div>
                <p className="text-[15px] font-medium text-ink">
                  {automation?.installed ? 'Windows 计划任务已安装' : '尚未安装 Windows 计划任务'}
                </p>
                <p className="mt-1 text-[13px] text-ink-secondary">
                  {automation?.message ?? '正在检查本机计划任务状态…'}
                </p>
              </div>
              <Pill tone={automation?.installed ? 'green' : 'gray'}>
                {automation?.installed ? automation.state : '未安装'}
              </Pill>
            </div>
            <dl className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-line p-3.5">
                <dt className="text-[12px] text-ink-tertiary">每日运行时间</dt>
                <dd className="mt-1 text-[16px] font-semibold text-ink">{draft.basic.dailyRunTime}</dd>
              </div>
              <div className="rounded-lg border border-line p-3.5">
                <dt className="text-[12px] text-ink-tertiary">下次运行</dt>
                <dd className="mt-1 text-[14px] font-medium text-ink">
                  {automation?.nextRunAt ? new Date(automation.nextRunAt).toLocaleString('zh-CN') : '安装后由 Windows 计算'}
                </dd>
              </div>
            </dl>
            <div className="rounded-lg bg-success-soft px-4 py-3 text-[13px] text-success">
              安装计划任务即表示允许每日监控在新页面或变化页面上调用 {draft.llm.provider}；单次调用范围受“抓取设置 → LLM 页面上限”约束。缓存命中页面不会重复调用。连接测试和申请材料仍需单独人工确认。
            </div>
            <div className="flex justify-end gap-2.5">
              {automation?.installed && (
                <Button variant="outline" onClick={() => setAutomationAction('remove')}>
                  移除计划任务
                </Button>
              )}
              <Button
                disabled={!automation?.supported}
                onClick={() => setAutomationAction('install')}
                className="bg-brand text-white hover:bg-brand-hover"
              >
                {automation?.installed ? '更新计划任务' : '安装每日计划任务'}
              </Button>
            </div>
          </Card>
        </TabsContent>

        {/* 数据与维护 */}
        <TabsContent value="data" className="mt-5">
          <div className="max-w-4xl space-y-5">
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardTitle>
                  <span className="flex items-center gap-2">
                    <Database className="size-4 text-ink-tertiary" />
                    数据库统计
                  </span>
                </CardTitle>
                <dl className="grid grid-cols-2 gap-3">
                  {[
                    { label: '岗位数', value: dbStats?.jobs ?? '–' },
                    { label: '岗位历史记录', value: dbStats?.history ?? '–' },
                    { label: '日报文件', value: dbStats?.reports ?? '–' },
                    { label: '运行日志', value: dbStats?.logs ?? '–' },
                    { label: '数据库大小', value: dbStats ? `${dbStats.sizeMb} MB` : '–' },
                  ].map((s) => (
                    <div key={s.label} className="rounded-lg bg-surface-subtle p-3.5">
                      <dd className="text-[20px] font-semibold text-ink tabular-nums">{s.value}</dd>
                      <dt className="text-[12px] text-ink-tertiary">{s.label}</dt>
                    </div>
                  ))}
                </dl>
              </Card>

              <Card>
                <CardTitle>
                  <span className="flex items-center gap-2">
                    <FolderCog className="size-4 text-ink-tertiary" />
                    维护操作
                  </span>
                </CardTitle>
                <div className="space-y-2.5">
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={async () => {
                      try {
                        const res = await runMaintenance('recalcMatch')
                        toast.success(res.message)
                      } catch (error) {
                        toast.error('操作失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
                      }
                    }}
                  >
                    <RefreshCw className="size-4" />
                    重新计算岗位匹配度
                  </Button>
                  <Button variant="outline" className="w-full justify-start" onClick={() => setDangerAction({ key: 'rebuildIndex', title: '重建岗位索引？', desc: '将根据现有岗位数据重建检索索引，期间搜索可能短暂变慢。数据本身不受影响。' })}>
                    <Database className="size-4" />
                    重建岗位索引
                  </Button>
                  <Button variant="outline" className="w-full justify-start" onClick={() => setDangerAction({ key: 'cleanReports', title: '清理历史日报？', desc: `将删除超过保留期（${draft.basic.reportRetentionDays} 天）的日报文件，不可恢复。` })}>
                    <Trash2 className="size-4" />
                    清理历史日报
                  </Button>
                  <Button variant="outline" className="w-full justify-start text-danger hover:text-danger" onClick={() => setDangerAction({ key: 'clearLogs', title: '清空运行日志？', desc: '将清空全部运行日志，任务统计与岗位数据保留。此操作不可撤销。' })}>
                    <Trash2 className="size-4" />
                    清空运行日志
                  </Button>
                </div>
              </Card>
            </div>

            <Card>
              <CardTitle
                extra={
                  <div className="flex items-center gap-2">
                    <Button variant="ghost" size="icon" aria-label="刷新备份列表" onClick={() => refetchBackups()}>
                      <RefreshCw className="size-4" />
                    </Button>
                    <Button
                      className="bg-brand text-white hover:bg-brand-hover"
                      onClick={() => setDangerAction({
                        key: 'export',
                        title: '创建本地完整备份？',
                        desc: `将在项目 private/backups 中创建私有 ZIP，并按已保存策略只保留最新 ${settings.basic.backupRetentionCount} 份；不包含 .env，也不会通过 API 下载。`,
                      })}
                    >
                      <Download className="size-4" />
                      创建备份
                    </Button>
                  </div>
                }
              >
                <span className="flex items-center gap-2">
                  <Archive className="size-4 text-brand" />
                  本地备份
                </span>
              </CardTitle>

              <div className="mb-4 flex flex-wrap items-end justify-between gap-3 rounded-lg bg-surface-subtle px-4 py-3.5">
                <Field label="自动保留数量" hint="更改后先保存；新备份创建成功后，只删除超出数量的最旧备份。">
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    aria-label="自动保留备份数量"
                    value={draft.basic.backupRetentionCount}
                    onChange={(event) => patch((state) => ({
                      ...state,
                      basic: { ...state.basic, backupRetentionCount: Number(event.target.value) },
                    }))}
                    className="w-32 rounded-lg bg-surface"
                  />
                </Field>
                <Button variant="outline" onClick={() => save('备份保留设置')} disabled={saveSettings.isPending}>
                  {saveSettings.isPending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  保存保留策略
                </Button>
              </div>

              {backupsLoading ? (
                <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-ink-secondary" role="status">
                  <Loader2 className="size-4 animate-spin" />
                  正在读取本地备份…
                </div>
              ) : backupsError ? (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-danger-soft px-4 py-3 text-[13px] text-danger" role="alert">
                  <span className="flex items-center gap-2"><CircleAlert className="size-4" />无法读取备份列表，请检查本地目录权限。</span>
                  <Button variant="outline" size="sm" onClick={() => refetchBackups()}>重试</Button>
                </div>
              ) : backups.length === 0 ? (
                <div className="py-10 text-center">
                  <Archive className="mx-auto size-7 text-ink-tertiary" />
                  <p className="mt-3 text-[14px] font-medium text-ink">还没有本地备份</p>
                  <p className="mt-1 text-[13px] text-ink-secondary">创建后可在这里查看、校验完整性或确认删除。</p>
                </div>
              ) : (
                <ul className="max-h-96 divide-y divide-line overflow-y-auto scrollbar-thin">
                  {backups.map((backup) => (
                    <li key={backup.name} className="flex flex-wrap items-center justify-between gap-3 py-3.5">
                      <div className="min-w-0 flex-1">
                        <p className="break-all text-[13px] font-medium text-ink">{backup.name}</p>
                        <p className="mt-1 text-[12px] text-ink-tertiary">
                          {formatBackupTime(backup.createdAt)} · {formatBackupSize(backup.sizeBytes)}
                          {backup.includedFiles === null ? '' : ` · ${backup.includedFiles} 个文件`}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center justify-end gap-2">
                        <BackupStatus status={backup.integrityStatus} />
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={verifyingBackup !== null}
                          onClick={async () => {
                            setVerifyingBackup(backup.name)
                            try {
                              const result = await verifyBackup(backup.name)
                              queryClient.setQueryData<BackupItem[]>(['backups'], (current = []) =>
                                current.map((item) => item.name === backup.name
                                  ? { ...item, integrityStatus: result.integrityStatus }
                                  : item),
                              )
                              if (result.ok) toast.success(result.message)
                              else toast.error('备份校验未通过', { description: result.message })
                            } catch (error) {
                              toast.error('无法校验备份', { description: error instanceof Error ? error.message : '请检查文件是否仍然存在。' })
                            } finally {
                              setVerifyingBackup(null)
                            }
                          }}
                        >
                          {verifyingBackup === backup.name ? <Loader2 className="size-4 animate-spin" /> : <BadgeCheck className="size-4" />}
                          {verifyingBackup === backup.name ? '校验中…' : '校验'}
                        </Button>
                        <Button variant="ghost" size="sm" className="text-danger hover:text-danger" onClick={() => setBackupToDelete(backup.name)}>
                          <Trash2 className="size-4" />
                          删除
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={automationAction !== null}
        onOpenChange={(open) => !open && setAutomationAction(null)}
        title={automationAction === 'remove' ? '移除每日计划任务？' : '安装每日计划任务？'}
        description={
          automationAction === 'remove'
            ? '将从 Windows 任务计划程序中移除 Career Radar，每日扫描不再自动启动。'
            : `将保存当前设置，并在 Windows 中创建每天 ${draft.basic.dailyRunTime} 运行的任务。新页面或变化页面可能调用 ${draft.llm.provider}，单次最多分析 ${draft.crawler.maxLlmPagesPerRun} 页；未变化页面使用缓存。`
        }
        confirmLabel={automationAction === 'remove' ? '确认移除' : '确认安装'}
        destructive={automationAction === 'remove'}
        onConfirm={async () => {
          const action = automationAction
          if (!action) return
          try {
            if (action === 'install') await saveSettings.mutateAsync(draft)
            await changeAutomation(action, draft.basic.dailyRunTime)
            await refetchAutomation()
            toast.success(action === 'install' ? '每日计划任务已安装' : '每日计划任务已移除')
          } catch (error) {
            toast.error('自动化设置失败', { description: error instanceof Error ? error.message : '请检查 Windows 任务计划程序。' })
          } finally {
            setAutomationAction(null)
          }
        }}
      />

      <ConfirmDialog
        open={llmConfirmOpen}
        onOpenChange={setLlmConfirmOpen}
        title={`确认测试 ${draft.llm.provider} 连接？`}
        description={`本次测试会向当前 ${draft.llm.provider} 模型发送一次最小结构化请求，可能产生少量 API 费用。系统不会自动重复测试。`}
        confirmLabel="确认并调用一次"
        onConfirm={async () => {
          setLlmConfirmOpen(false)
          setLlmTesting(true)
          try {
            const res = await testLlmConnection(true)
            toast.success(`${draft.llm.provider} 连接正常`, { description: `模型 ${res.model} · 延迟 ${res.latencyMs}ms` })
          } catch (error) {
            toast.error(`${draft.llm.provider} 连接失败`, { description: error instanceof Error ? error.message : '请检查 API 配置。' })
          } finally {
            setLlmTesting(false)
          }
        }}
      />

      <ConfirmDialog
        open={!!dangerAction}
        onOpenChange={(v) => !v && setDangerAction(null)}
        title={dangerAction?.title ?? ''}
        description={dangerAction?.desc ?? ''}
        confirmLabel={dangerAction?.key === 'export' ? '创建本地备份' : '确认执行'}
        destructive={dangerAction?.key === 'clearLogs' || dangerAction?.key === 'cleanReports'}
        onConfirm={async () => {
          try {
            if (dangerAction) {
              const res = await runMaintenance(dangerAction.key)
              if (dangerAction.key === 'export') {
                await queryClient.invalidateQueries({ queryKey: ['backups'] })
              }
              toast.success(res.message, {
                description: res.prunedBackups
                  ? `已按保留策略清理 ${res.prunedBackups} 份最旧备份。`
                  : undefined,
              })
            }
          } catch (error) {
            toast.error('维护操作失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
          } finally {
            setDangerAction(null)
          }
        }}
      />

      <ConfirmDialog
        open={backupToDelete !== null}
        onOpenChange={(open) => !open && setBackupToDelete(null)}
        title="删除这份本地备份？"
        description={backupToDelete
          ? `将永久删除 ${backupToDelete}。备份包含私有配置和运行数据，删除后无法从 Career Radar 恢复。`
          : ''}
        confirmLabel="确认删除备份"
        destructive
        confirmDisabled={deletingBackup}
        onConfirm={async () => {
          const name = backupToDelete
          if (!name) return
          setDeletingBackup(true)
          try {
            const result = await deleteBackup(name, true)
            await queryClient.invalidateQueries({ queryKey: ['backups'] })
            toast.success(result.message)
          } catch (error) {
            toast.error('备份删除失败', { description: error instanceof Error ? error.message : '请检查文件是否被其他程序占用。' })
          } finally {
            setDeletingBackup(false)
            setBackupToDelete(null)
          }
        }}
      />
    </div>
  )
}
