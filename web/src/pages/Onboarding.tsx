import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Radar, ArrowLeft, ArrowRight, Check, Plus, Building2, Loader2, PlugZap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Slider } from '@/components/ui/slider'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Card, CardTitle } from '@/components/common/PageHeader'
import { Pill } from '@/components/common/Badges'
import { useCompanies } from '@/hooks/useCompanies'
import { addCompany, testCompanyConnection, updateCompany } from '@/services/companies'
import { createRun } from '@/services/runs'
import { getProfile, getSettings, saveProfile, saveSettings } from '@/services/settings'
import { cn } from '@/lib/utils'

const ROLE_OPTIONS = ['AI 应用', '数据分析', '产品助理', '测试', '运维', '后端开发', '前端开发', '内容运营', '其他']
const STEP_TITLES = ['建立求职画像', '添加监控企业', '设置扫描规则', '通知方式']

function MultiSelect({ options, values, onChange }: { options: string[]; values: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const active = values.includes(opt)
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(active ? values.filter((v) => v !== opt) : [...values, opt])}
            className={cn(
              'rounded-md px-3 py-1.5 text-[13px] transition-colors',
              active ? 'bg-brand-soft text-brand-foreground font-medium' : 'bg-black/[0.04] text-ink-secondary hover:bg-black/[0.07]',
            )}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}

export default function OnboardingPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [baselineOpen, setBaselineOpen] = useState(false)
  const [testing, setTesting] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const { data: configuredCompanies } = useCompanies()

  // 第 1 步
  const [gradYear, setGradYear] = useState('2026 届')
  const [degree, setDegree] = useState('本科')
  const [major, setMajor] = useState('')
  const [roles, setRoles] = useState<string[]>(['AI 应用'])
  const [cities, setCities] = useState<string[]>(['上海'])
  const [salary, setSalary] = useState<[number, number]>([8, 15])
  const [skillsText, setSkillsText] = useState('')
  const [acceptInternship, setAcceptInternship] = useState(true)
  const [acceptRelocation, setAcceptRelocation] = useState(true)
  const [maxDifficulty, setMaxDifficulty] = useState(6)

  // 第 2 步
  const [uncheckedCompanies, setUncheckedCompanies] = useState<Set<string>>(new Set())
  const [customUrl, setCustomUrl] = useState('')

  // 第 3 步
  const [runTime, setRunTime] = useState('09:30')
  const [delay, setDelay] = useState('2-6')
  const [playwrightFallback, setPlaywrightFallback] = useState(true)
  const [maxPages, setMaxPages] = useState('20')
  const [campusOnly, setCampusOnly] = useState(true)
  const [changeDetect, setChangeDetect] = useState(true)

  // 第 4 步
  const [genMarkdown, setGenMarkdown] = useState(true)
  const [genCsv, setGenCsv] = useState(true)
  const [emailEnabled, setEmailEnabled] = useState(false)
  const [notifyTypes, setNotifyTypes] = useState<string[]>(['新增岗位', '高匹配岗位'])
  const [notifyMaxDifficulty, setNotifyMaxDifficulty] = useState(7)
  const [minMatch, setMinMatch] = useState('medium')

  const recommended = configuredCompanies ?? []

  const finish = async (sendEmail: boolean) => {
    setFinishing(true)
    try {
      const [currentProfile, currentSettings] = await Promise.all([getProfile(), getSettings()])
      const parsedSkills = skillsText
        .split(/[，,\n]/)
        .map((item) => item.trim())
        .filter(Boolean)
        .map((name) => currentProfile.skills.find((skill) => skill.name === name) ?? { name, level: '了解' as const })
      await saveProfile({
        ...currentProfile,
        gradYear,
        degree,
        major: major.trim() || currentProfile.major,
        targetRoles: roles,
        cities,
        salaryRange: salary,
        skills: parsedSkills.length ? parsedSkills : currentProfile.skills,
        acceptInternship,
        acceptRelocation,
        maxDifficulty,
        workTypes: campusOnly ? ['校招', '实习'] : currentProfile.workTypes,
      })

      const [minDelay, maxDelay] = delay.split('-').map(Number)
      const smtpReady = Boolean(currentSettings.email.smtpHost && currentSettings.email.fromAddress && currentSettings.email.toAddresses.length)
      await saveSettings({
        ...currentSettings,
        basic: { ...currentSettings.basic, dailyRunTime: runTime },
        crawler: {
          ...currentSettings.crawler,
          minDelay,
          maxDelay,
          maxPagesPerCompany: Number(maxPages),
          defaultRenderMode: playwrightFallback ? 'auto' : 'static',
        },
        email: {
          ...currentSettings.email,
          enabled: emailEnabled && smtpReady,
          sendOnUpdate: changeDetect && notifyTypes.includes('更新岗位'),
          minMatchLevel: minMatch as 'high' | 'medium' | 'low',
          maxDifficulty: notifyMaxDifficulty,
        },
      })

      await Promise.all(
        recommended
          .filter((company) => company.enabled === uncheckedCompanies.has(company.id))
          .map((company) => updateCompany(company.id, { enabled: !uncheckedCompanies.has(company.id) })),
      )

      if (customUrl.trim()) {
        const url = new URL(customUrl.trim())
        await addCompany({
          name: url.hostname.replace(/^www\./, ''),
          website: url.origin,
          careersUrl: customUrl.trim(),
          companyType: 'private',
          renderMode: 'auto',
          maxPages: Number(maxPages),
          enabled: true,
        })
      }

      const result = await createRun({ scope: 'all', sendEmail: sendEmail && emailEnabled && smtpReady })
      setBaselineOpen(false)
      if (emailEnabled && !smtpReady) {
        toast.warning('SMTP 尚未配置完整，本次仅生成本地日报。')
      }
      toast.success('配置已保存，真实首次扫描已开始')
      navigate(`/runs/${result.runId}`)
    } catch (error) {
      toast.error('保存配置或创建扫描失败', {
        description: error instanceof Error ? error.message : '请确认本地 API 正常运行。',
      })
    } finally {
      setFinishing(false)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* 顶部 */}
      <header className="mx-auto flex h-16 max-w-3xl items-center justify-between px-6">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-brand text-white">
            <Radar className="size-4" />
          </span>
          <span className="text-[15px] font-semibold text-ink">Career Radar</span>
        </div>
        <button onClick={() => navigate('/')} className="text-[13px] text-ink-secondary hover:text-ink transition-colors">
          跳过配置
        </button>
      </header>

      <main className="mx-auto max-w-3xl px-6 pb-16">
        {/* 步骤条 */}
        <ol className="mb-8 flex items-center">
          {STEP_TITLES.map((t, i) => (
            <li key={t} className={cn('flex items-center', i < STEP_TITLES.length - 1 && 'flex-1')}>
              <div className="flex items-center gap-2.5">
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-medium transition-colors',
                    i < step
                      ? 'bg-success text-white'
                      : i === step
                        ? 'bg-brand text-white'
                        : 'bg-black/[0.06] text-ink-tertiary',
                  )}
                >
                  {i < step ? <Check className="size-4" /> : i + 1}
                </span>
                <span className={cn('hidden text-[13px] sm:block', i === step ? 'font-medium text-ink' : 'text-ink-tertiary')}>
                  {t}
                </span>
              </div>
              {i < STEP_TITLES.length - 1 && <span className="mx-3 h-px flex-1 bg-black/[0.08]" />}
            </li>
          ))}
        </ol>

        {/* 第 1 步：求职画像 */}
        {step === 0 && (
          <Card className="space-y-5">
            <CardTitle>第 1 步 · 建立求职画像</CardTitle>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>毕业届别</Label>
                <Select value={gradYear} onValueChange={setGradYear}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['2025 届', '2026 届', '2027 届'].map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>学历</Label>
                <Select value={degree} onValueChange={setDegree}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {['大专', '本科', '硕士', '博士'].map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>专业</Label>
              <Input value={major} onChange={(e) => setMajor(e.target.value)} placeholder="例如：计算机科学与技术" className="rounded-lg" />
            </div>
            <div className="space-y-1.5">
              <Label>目标岗位方向（可多选）</Label>
              <MultiSelect options={ROLE_OPTIONS} values={roles} onChange={setRoles} />
            </div>
            <div className="space-y-1.5">
              <Label>期望城市</Label>
              <MultiSelect options={['上海', '北京', '杭州', '深圳', '广州', '成都', '远程']} values={cities} onChange={setCities} />
            </div>
            <div className="space-y-2">
              <Label>薪资范围（K/月）：{salary[0]}K – {salary[1]}K</Label>
              <Slider value={salary} min={3} max={40} step={1} onValueChange={(v) => setSalary([v[0], v[1]])} />
            </div>
            <div className="space-y-1.5">
              <Label>当前技能</Label>
              <Input value={skillsText} onChange={(e) => setSkillsText(e.target.value)} placeholder="用逗号分隔，如：Python, SQL, RAG" className="rounded-lg" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-3.5 py-3">
                <span className="text-[14px] text-ink">接受实习</span>
                <Switch checked={acceptInternship} onCheckedChange={setAcceptInternship} />
              </div>
              <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-3.5 py-3">
                <span className="text-[14px] text-ink">接受异地</span>
                <Switch checked={acceptRelocation} onCheckedChange={setAcceptRelocation} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>最大岗位难度：{maxDifficulty}/10</Label>
              <Slider value={[maxDifficulty]} min={1} max={10} step={1} onValueChange={(v) => setMaxDifficulty(v[0])} />
            </div>
          </Card>
        )}

        {/* 第 2 步：添加监控企业 */}
        {step === 1 && (
          <div className="space-y-5">
            <Card>
              <CardTitle>第 2 步 · 添加监控企业</CardTitle>
              <p className="mb-4 text-[13px] text-ink-secondary">
                勾选想监控的企业，系统会自动寻找其官网的招聘入口。也可以手动添加或批量导入。
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                {recommended.map((c) => {
                  const checked = !uncheckedCompanies.has(c.id)
                  return (
                    <label
                      key={c.id}
                      className={cn(
                        'flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors',
                        checked ? 'border-brand/40 bg-brand-soft/50' : 'border-black/[0.08] hover:border-black/[0.16]',
                      )}
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={(v) =>
                          setUncheckedCompanies((prev) => {
                            const next = new Set(prev)
                            if (v === true) next.delete(c.id)
                            else next.add(c.id)
                            return next
                          })
                        }
                        className="mt-0.5"
                      />
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 text-[14px] font-medium text-ink">
                          {c.name}
                          <Pill tone={c.status === 'active' ? 'green' : 'gray'}>{c.status === 'active' ? '监控中' : '待验证'}</Pill>
                        </p>
                        <p className="mt-0.5 truncate text-[12px] text-ink-tertiary">{c.website}</p>
                        <p className="text-[12px] text-ink-tertiary">{c.industry}{c.careersUrl ? ' · 已识别招聘入口' : ''}</p>
                      </div>
                    </label>
                  )
                })}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <div className="flex flex-1 min-w-56 gap-2">
                  <Input
                    value={customUrl}
                    onChange={(e) => setCustomUrl(e.target.value)}
                    placeholder="手动添加企业官网地址，如 https://example.com"
                    className="h-9 rounded-lg"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 shrink-0"
                    onClick={async () => {
                      if (!customUrl.trim()) {
                        toast.error('请先填写企业官网地址')
                        return
                      }
                      setTesting(true)
                      try {
                        const res = await testCompanyConnection(customUrl.trim())
                        if (res.entryFound) {
                          toast.success('测试连接通过', { description: `已识别招聘入口：${res.entryUrl}` })
                        } else {
                          toast.warning('首页可访问，但未识别到招聘入口', { description: '完成配置时仍会按该地址保存。' })
                        }
                      } catch (error) {
                        toast.error('连接测试失败', { description: error instanceof Error ? error.message : '请检查网址。' })
                      } finally {
                        setTesting(false)
                      }
                    }}
                  >
                    {testing ? <Loader2 className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                    测试招聘入口
                  </Button>
                </div>
                <Button variant="ghost" size="sm" className="h-9 text-ink-secondary" onClick={() => toast.info('批量导入支持 CSV，每行：企业名称,官网地址')}>
                  <Plus className="size-4" />
                  批量导入
                </Button>
              </div>
            </Card>
          </div>
        )}

        {/* 第 3 步：扫描规则 */}
        {step === 2 && (
          <Card className="space-y-5">
            <CardTitle>第 3 步 · 设置扫描规则</CardTitle>
            <p className="text-[13px] text-ink-secondary">默认值安全、合规、保守，建议首次使用保持不变。</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>每日运行时间</Label>
                <Input type="time" value={runTime} onChange={(e) => setRunTime(e.target.value)} className="rounded-lg" />
              </div>
              <div className="space-y-1.5">
                <Label>同域请求间隔（秒）</Label>
                <Select value={delay} onValueChange={setDelay}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="2-6">2 ~ 6 秒（推荐）</SelectItem>
                    <SelectItem value="5-10">5 ~ 10 秒（更保守）</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>单家公司最大页面数</Label>
                <Input type="number" min={1} max={100} value={maxPages} onChange={(e) => setMaxPages(e.target.value)} className="rounded-lg" />
              </div>
            </div>
            {[
              { label: 'Playwright 自动回退', desc: '静态抓取内容不足时，自动切换浏览器渲染', value: playwrightFallback, set: setPlaywrightFallback },
              { label: '仅保留校招和实习岗位', desc: '过滤社招岗位，减少噪音', value: campusOnly, set: setCampusOnly },
              { label: '启用岗位变化检测', desc: 'JD 或投递入口变化时标记「已更新」', value: changeDetect, set: setChangeDetect },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                <div>
                  <p className="text-[14px] font-medium text-ink">{item.label}</p>
                  <p className="text-[12px] text-ink-tertiary">{item.desc}</p>
                </div>
                <Switch checked={item.value} onCheckedChange={item.set} />
              </div>
            ))}
          </Card>
        )}

        {/* 第 4 步：通知方式 */}
        {step === 3 && (
          <Card className="space-y-5">
            <CardTitle>第 4 步 · 通知方式</CardTitle>
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                { label: '生成 Markdown 日报', desc: '适合阅读的每日简报', value: genMarkdown, set: setGenMarkdown },
                { label: '生成 CSV 日报', desc: '适合 Excel 筛选分析', value: genCsv, set: setGenCsv },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
                  <div>
                    <p className="text-[14px] font-medium text-ink">{item.label}</p>
                    <p className="text-[12px] text-ink-tertiary">{item.desc}</p>
                  </div>
                  <Switch checked={item.value} onCheckedChange={item.set} disabled />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-4 py-3">
              <div>
                <p className="text-[14px] font-medium text-ink">启用邮件提醒</p>
                <p className="text-[12px] text-ink-tertiary">需要先在系统设置中配置 SMTP</p>
              </div>
              <Switch checked={emailEnabled} onCheckedChange={setEmailEnabled} />
            </div>
            <div className="space-y-1.5">
              <Label>通知哪些类型岗位</Label>
              <MultiSelect options={['新增岗位', '高匹配岗位', '更新岗位', '岗位关闭提醒']} values={notifyTypes} onChange={setNotifyTypes} />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>最大岗位难度：{notifyMaxDifficulty}/10</Label>
                <Slider value={[notifyMaxDifficulty]} min={1} max={10} step={1} onValueChange={(v) => setNotifyMaxDifficulty(v[0])} />
              </div>
              <div className="space-y-1.5">
                <Label>最低能力匹配等级</Label>
                <Select value={minMatch} onValueChange={setMinMatch}>
                  <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="high">仅高匹配</SelectItem>
                    <SelectItem value="medium">中匹配及以上</SelectItem>
                    <SelectItem value="low">全部岗位</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </Card>
        )}

        {/* 底部操作 */}
        <div className="mt-6 flex items-center justify-between">
          <Button variant="ghost" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
            <ArrowLeft className="size-4" />
            {step === 0 ? '返回' : '返回上一步'}
          </Button>
          {step < 3 ? (
            <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => setStep((s) => s + 1)}>
              保存并继续
              <ArrowRight className="size-4" />
            </Button>
          ) : (
            <Button className="bg-brand hover:bg-brand-hover text-white" onClick={() => setBaselineOpen(true)}>
              完成配置并开始首次扫描
            </Button>
          )}
        </div>
      </main>

      {/* 基线确认弹窗 */}
      <AlertDialog open={baselineOpen} onOpenChange={setBaselineOpen}>
        <AlertDialogContent className="rounded-xl">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-ink">
              <Building2 className="size-5 text-brand" />
              首次扫描将建立岗位基线
            </AlertDialogTitle>
            <AlertDialogDescription className="leading-relaxed">
              首次扫描会将企业官网现有岗位建立为基线，可能产生较多「新增岗位」记录。建议首次运行不发送邮件。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:justify-end">
            <AlertDialogCancel onClick={() => finish(false)} disabled={finishing}>仅建立基线</AlertDialogCancel>
            <AlertDialogAction onClick={() => finish(true)} disabled={finishing} className="bg-brand hover:bg-brand-hover">
              {finishing ? '正在保存并创建任务…' : '建立基线并发送通知'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
