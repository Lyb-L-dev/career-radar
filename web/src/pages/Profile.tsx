import { useState } from 'react'
import { toast } from 'sonner'
import { Plus, X, RotateCcw, Save, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Progress } from '@/components/ui/progress'
import { Textarea } from '@/components/ui/textarea'
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
import { useProfile, useSaveProfile } from '@/hooks/useData'
import { recalculateMatch } from '@/services/settings'
import type { CandidateProfile, SkillLevel, SkillTag } from '@/types'
import { cn } from '@/lib/utils'

const ROLE_OPTIONS = ['AI 应用', '数据分析', '产品助理', '测试', '运维', '后端开发', '前端开发', '内容运营', '其他']
const SKILL_LEVELS: SkillLevel[] = ['了解', '熟悉', '熟练']

function TagPicker({
  options,
  values,
  onChange,
}: {
  options: string[]
  values: string[]
  onChange: (v: string[]) => void
}) {
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

export default function ProfilePage() {
  const { data: profile, isLoading, isError, refetch } = useProfile()

  if (isLoading) return <PageSkeleton />
  if (isError || !profile) return <ErrorState onRetry={() => refetch()} />

  return <ProfileEditor key={JSON.stringify(profile)} profile={profile} />
}

function ProfileEditor({ profile }: { profile: CandidateProfile }) {
  const saveProfile = useSaveProfile()
  const [draft, setDraft] = useState<CandidateProfile>(profile)
  const [newSkill, setNewSkill] = useState('')
  const [discardOpen, setDiscardOpen] = useState(false)
  const [recalcing, setRecalcing] = useState(false)

  const dirty = JSON.stringify(draft) !== JSON.stringify(profile)
  const patch = (p: Partial<CandidateProfile>) => setDraft({ ...draft, ...p })
  const patchSkill = (name: string, level: SkillLevel) =>
    patch({ skills: draft.skills.map((s) => (s.name === name ? { ...s, level } : s)) })
  const removeSkill = (name: string) => patch({ skills: draft.skills.filter((s) => s.name !== name) })
  const addSkill = () => {
    const name = newSkill.trim()
    if (!name) return
    if (draft.skills.some((s) => s.name === name)) {
      toast.error('这个技能已存在')
      return
    }
    patch({ skills: [...draft.skills, { name, level: '了解' } as SkillTag] })
    setNewSkill('')
  }

  const doSave = async (recalc: boolean) => {
    try {
      await saveProfile.mutateAsync(draft)
      if (recalc) {
        setRecalcing(true)
        const res = await recalculateMatch()
        toast.success('画像已保存', { description: res.updated > 0 ? `已更新 ${res.updated} 个岗位的匹配结果。` : '新画像将在下一次真实扫描时参与评分。' })
      } else {
        toast.success('画像已保存')
      }
    } catch (error) {
      toast.error('保存画像失败', {
        description: error instanceof Error ? error.message : '请确认本地 API 正常运行。',
      })
    } finally {
      setRecalcing(false)
    }
  }

  return (
    <div className="space-y-5 pb-24">
      <PageHeader title="我的求职画像" subtitle="画像越完整，岗位匹配与推荐越准确" />

      {/* 完整度 */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-56">
            <div className="flex items-baseline justify-between">
              <p className="text-[15px] font-medium text-ink">当前画像完整度 {draft.completeness}%</p>
              <p className="text-[12px] text-ink-tertiary">补充项目经历可提高岗位匹配准确性</p>
            </div>
            <Progress value={draft.completeness} className="mt-2 h-2" />
          </div>
        </div>
      </Card>

      <div className="grid gap-5 xl:grid-cols-2">
        {/* 左栏：基础信息 */}
        <Card className="space-y-5">
          <CardTitle>基础信息</CardTitle>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>毕业届别</Label>
              <Select value={draft.gradYear} onValueChange={(v) => patch({ gradYear: v })}>
                <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['2025 届', '2026 届', '2027 届'].map((y) => <SelectItem key={y} value={y}>{y}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>学历</Label>
              <Select value={draft.degree} onValueChange={(v) => patch({ degree: v })}>
                <SelectTrigger className="rounded-lg"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['大专', '本科', '硕士', '博士'].map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="major">专业</Label>
            <Input id="major" value={draft.major} onChange={(e) => patch({ major: e.target.value })} className="rounded-lg" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="school-background">院校背景</Label>
            <Input
              id="school-background"
              value={draft.schoolBackground}
              onChange={(e) => patch({ schoolBackground: e.target.value })}
              className="rounded-lg"
            />
          </div>
          <div className="space-y-1.5">
            <Label>目标岗位方向</Label>
            <TagPicker options={ROLE_OPTIONS} values={draft.targetRoles} onChange={(v) => patch({ targetRoles: v })} />
          </div>
          <div className="space-y-1.5">
            <Label>期望城市</Label>
            <TagPicker options={['上海', '北京', '杭州', '深圳', '广州', '成都', '远程']} values={draft.cities} onChange={(v) => patch({ cities: v })} />
          </div>
          <div className="space-y-2">
            <Label>薪资范围（K/月）：{draft.salaryRange[0]}K – {draft.salaryRange[1]}K</Label>
            <Slider
              value={draft.salaryRange}
              min={3}
              max={40}
              step={1}
              onValueChange={(v) => patch({ salaryRange: [v[0], v[1]] as [number, number] })}
            />
          </div>
          <div className="space-y-2">
            <Label>最大岗位难度：{draft.maxDifficulty}/10</Label>
            <Slider
              value={[draft.maxDifficulty]}
              min={1}
              max={10}
              step={1}
              onValueChange={(v) => patch({ maxDifficulty: v[0] })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-3.5 py-3">
              <span className="text-[14px] text-ink">接受实习</span>
              <Switch checked={draft.acceptInternship} onCheckedChange={(v) => patch({ acceptInternship: v })} />
            </div>
            <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-3.5 py-3">
              <span className="text-[14px] text-ink">接受异地</span>
              <Switch checked={draft.acceptRelocation} onCheckedChange={(v) => patch({ acceptRelocation: v })} />
            </div>
          </div>
        </Card>

        {/* 右栏：能力标签 + 项目 */}
        <div className="space-y-5">
          <Card>
            <CardTitle>能力标签</CardTitle>
            <div className="space-y-2.5">
              {draft.skills.map((s) => (
                <div key={s.name} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 text-[13px] font-medium text-ink">{s.name}</span>
                  <div className="flex gap-1">
                    {SKILL_LEVELS.map((lv) => (
                      <button
                        key={lv}
                        type="button"
                        onClick={() => patchSkill(s.name, lv)}
                        className={cn(
                          'rounded-md px-2.5 py-1 text-[12px] transition-colors',
                          s.level === lv ? 'bg-brand-soft text-brand-foreground font-medium' : 'text-ink-tertiary hover:bg-black/[0.04]',
                        )}
                      >
                        {lv}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeSkill(s.name)}
                    className="ml-auto text-ink-tertiary hover:text-danger transition-colors"
                    aria-label={`删除技能 ${s.name}`}
                  >
                    <X className="size-4" />
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <Input
                value={newSkill}
                onChange={(e) => setNewSkill(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addSkill()}
                placeholder="添加技能，如 Docker、Spark…"
                className="h-9 rounded-lg"
              />
              <Button variant="outline" size="sm" className="h-9" onClick={addSkill}>
                <Plus className="size-4" />
                添加
              </Button>
            </div>
          </Card>

          <Card>
            <CardTitle
              extra={
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-brand"
                  onClick={() => patch({ internships: [...draft.internships, ''] })}
                >
                  <Plus className="size-4" />
                  添加实习经历
                </Button>
              }
            >
              实习经历
            </CardTitle>
            {draft.internships.length === 0 ? (
              <p className="text-[13px] text-ink-tertiary">暂无正式实习经历，可如实保留为空。</p>
            ) : (
              <div className="space-y-2.5">
                {draft.internships.map((item, index) => (
                  <div key={`${index}-${item.slice(0, 16)}`} className="flex items-start gap-2">
                    <Textarea
                      value={item}
                      onChange={(e) => patch({ internships: draft.internships.map((value, i) => i === index ? e.target.value : value) })}
                      rows={2}
                      className="rounded-lg"
                      placeholder="公司、岗位、工作内容与结果"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="shrink-0 text-ink-tertiary hover:text-danger"
                      onClick={() => patch({ internships: draft.internships.filter((_, i) => i !== index) })}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardTitle>画像补充说明</CardTitle>
            <Textarea
              value={draft.notes}
              onChange={(e) => patch({ notes: e.target.value })}
              rows={4}
              className="rounded-lg"
              placeholder="奖项、学生工作、求职优势等会影响岗位判断的信息"
            />
          </Card>

          <Card>
            <CardTitle
              extra={
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-brand"
                  onClick={() =>
                    patch({
                      projects: [
                        ...draft.projects,
                        { id: `p-${Date.now()}`, name: '', description: '', skills: [] },
                      ],
                    })
                  }
                >
                  <Plus className="size-4" />
                  添加项目经历
                </Button>
              }
            >
              项目经历
            </CardTitle>
            {draft.projects.length === 0 ? (
              <p className="text-[13px] text-ink-tertiary">还没有项目经历，添加一段可以显著提高匹配准确性。</p>
            ) : (
              <div className="space-y-4">
                {draft.projects.map((p) => (
                  <div key={p.id} className="space-y-2.5 rounded-lg bg-surface-subtle p-4">
                    <div className="flex items-center gap-2">
                      <Input
                        value={p.name}
                        onChange={(e) =>
                          patch({ projects: draft.projects.map((x) => (x.id === p.id ? { ...x, name: e.target.value } : x)) })
                        }
                        placeholder="项目名称"
                        className="h-9 rounded-lg bg-surface"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-9 shrink-0 text-ink-tertiary hover:text-danger"
                        aria-label="删除项目"
                        onClick={() => patch({ projects: draft.projects.filter((x) => x.id !== p.id) })}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                    <Textarea
                      value={p.description}
                      onChange={(e) =>
                        patch({ projects: draft.projects.map((x) => (x.id === p.id ? { ...x, description: e.target.value } : x)) })
                      }
                      placeholder="用两三句话描述项目背景、你的角色和用到的技术…"
                      rows={3}
                      className="rounded-lg bg-surface"
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {p.skills.map((s) => (
                        <Pill key={s} tone="blue">{s}</Pill>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardTitle>不感兴趣方向</CardTitle>
            <p className="mb-3 text-[12px] text-ink-tertiary">这些方向的岗位将降低推荐权重。</p>
            <TagPicker
              options={['销售', '客服', '硬件嵌入式', '测试外包', '驻场运维', '低代码实施']}
              values={draft.excludedDirections}
              onChange={(v) => patch({ excludedDirections: v })}
            />
          </Card>
        </div>
      </div>

      {/* 底部固定操作栏 */}
      <div className="fixed bottom-0 left-0 right-0 z-30 border-t border-black/[0.06] bg-surface/95 backdrop-blur md:left-56">
        <div className="mx-auto flex max-w-[1440px] items-center gap-3 px-4 py-3 md:px-8">
          <p className="text-[12px] text-ink-tertiary">
            {dirty ? '有未保存的修改' : '所有修改已保存'}
          </p>
          <div className="ml-auto flex items-center gap-2.5">
            <Button variant="ghost" disabled={!dirty} onClick={() => setDiscardOpen(true)}>
              <RotateCcw className="size-4" />
              放弃修改
            </Button>
            <Button variant="outline" disabled={!dirty || saveProfile.isPending} onClick={() => doSave(false)}>
              <Save className="size-4" />
              {saveProfile.isPending ? '保存中…' : '保存画像'}
            </Button>
            <Button
              className="bg-brand hover:bg-brand-hover text-white"
              disabled={saveProfile.isPending || recalcing}
              onClick={() => doSave(true)}
            >
              <RefreshCw className={cn('size-4', recalcing && 'animate-spin')} />
              {recalcing ? '正在重新计算…' : '保存并重新计算匹配度'}
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title="放弃未保存的修改？"
        description="当前页面中的修改将恢复为上次保存的内容，此操作不可撤销。"
        confirmLabel="放弃修改"
        destructive
        onConfirm={() => {
          setDraft(profile)
          setDiscardOpen(false)
          toast.success('已恢复为上次保存的内容')
        }}
      />
    </div>
  )
}
