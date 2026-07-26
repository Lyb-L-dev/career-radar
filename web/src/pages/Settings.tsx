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
import { testLlmConnection, sendTestEmail, runMaintenance, getDbStats } from '@/services/settings'
import type { AppSettings, RenderMode, MatchLevel } from '@/types'
import { MATCH_LEVEL_LABEL } from '@/types'
import { useQuery } from '@tanstack/react-query'

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

  return <SettingsEditor key={JSON.stringify(settings)} settings={settings} initialTab={tabParam === 'email' ? 'email' : 'basic'} />
}

function SettingsEditor({ settings, initialTab }: { settings: AppSettings; initialTab: string }) {
  const saveSettings = useSaveSettings()
  const [draft, setDraft] = useState<AppSettings>(settings)
  const [tab, setTab] = useState(initialTab)
  const [llmTesting, setLlmTesting] = useState(false)
  const [emailTesting, setEmailTesting] = useState(false)
  const [dangerAction, setDangerAction] = useState<null | { key: 'clearLogs' | 'rebuildIndex' | 'cleanReports'; title: string; desc: string }>(null)
  const { data: dbStats } = useQuery({ queryKey: ['db-stats'], queryFn: getDbStats })

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
              <Field label="日报保留天数">
                <Input
                  type="number"
                  min={7}
                  max={365}
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
              <Field label="服务商">
                <Select
                  value={draft.llm.provider}
                  onValueChange={(v) => patch((s) => ({ ...s, llm: { ...s.llm, provider: v as AppSettings['llm']['provider'] } }))}
                >
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="DeepSeek">DeepSeek</SelectItem>
                    <SelectItem value="OpenAI">OpenAI</SelectItem>
                    <SelectItem value="Anthropic">Anthropic</SelectItem>
                  </SelectContent>
                </Select>
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
                onClick={async () => {
                  setLlmTesting(true)
                  try {
                    const res = await testLlmConnection()
                    toast.success('LLM 连接正常', { description: `模型 ${res.model} · 延迟 ${res.latencyMs}ms` })
                  } catch (error) {
                    toast.error('LLM 连接失败', { description: error instanceof Error ? error.message : '请检查 API 配置。' })
                  } finally {
                    setLlmTesting(false)
                  }
                }}
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
          </div>
        </TabsContent>

        {/* 数据与维护 */}
        <TabsContent value="data" className="mt-5">
          <div className="grid max-w-4xl gap-5 lg:grid-cols-2">
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
                      const res = await runMaintenance('export')
                      toast.success(res.message)
                    } catch (error) {
                      toast.error('无法自动导出', { description: error instanceof Error ? error.message : '请手工备份数据。' })
                    }
                  }}
                >
                  <Download className="size-4" />
                  导出全部数据
                </Button>
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
                <Button variant="outline" className="w-full justify-start text-danger hover:text-danger" onClick={() => setDangerAction({ key: 'clearLogs', title: '清空运行日志？', desc: '将删除全部运行日志（约 128 条），任务统计与岗位数据保留。此操作不可撤销。' })}>
                  <Trash2 className="size-4" />
                  清空运行日志
                </Button>
              </div>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={!!dangerAction}
        onOpenChange={(v) => !v && setDangerAction(null)}
        title={dangerAction?.title ?? ''}
        description={dangerAction?.desc ?? ''}
        confirmLabel="确认执行"
        destructive
        onConfirm={async () => {
          try {
            if (dangerAction) {
              const res = await runMaintenance(dangerAction.key)
              toast.success(res.message)
            }
          } catch (error) {
            toast.error('维护操作失败', { description: error instanceof Error ? error.message : '请稍后重试。' })
          } finally {
            setDangerAction(null)
          }
        }}
      />
    </div>
  )
}
