import { useState } from 'react'
import { CheckCircle2, CircleHelp, RotateCcw, ArrowRight, ChevronDown, ChevronRight } from 'lucide-react'
import type { GrowthSkill } from '@/services/growth'
import { SKILL_STATUS, layoutGrowthSkills } from '@/lib/growthMap'

export default function GrowthRoadmap({ skills, groups, selected, onSelect }: { skills: GrowthSkill[]; groups: string[]; selected: string | null; onSelect: (id: string) => void }) {
  const [all, setAll] = useState(false)
  const [collapsed, setCollapsed] = useState<string[]>([])
  const shown = skills.filter((skill) => (all || skill.relevant) && !collapsed.includes(skill.group))
  const positioned = layoutGrowthSkills(shown)
  const width = Math.max(320, ...positioned.map((s) => s.x + 160))
  const height = Math.max(160, ...positioned.map((s) => s.y + 120))
  const choose = (id: string) => onSelect(id)
  const node = (skill: GrowthSkill) => <><span className="block text-xs text-ink-secondary">{skill.group}</span><span className="mt-1 block font-semibold text-ink">{skill.name}</span><span className="mt-2 flex items-center gap-1.5 text-xs">{skill.level >= 2 ? <CheckCircle2 className="size-3.5 text-success" /> : <CircleHelp className="size-3.5 text-ink-secondary" />}<span>{skill.level ? `L${skill.level} / 5 · ${SKILL_STATUS[skill.status]}` : SKILL_STATUS[skill.status]}</span></span>{skill.reviewDue ? <span className="mt-1 inline-flex items-center gap-1 text-xs text-amber-800"><RotateCcw className="size-3" />待复习</span> : skill.recommended ? <span className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-foreground">建议下一步 <ArrowRight className="size-3" /></span> : null}</>
  return <section aria-label="能力路线图" className="min-w-0">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2">{groups.filter((group) => skills.some((s) => s.group === group && (all || s.relevant))).map((group) => <button key={group} type="button" aria-expanded={!collapsed.includes(group)} onClick={() => setCollapsed((old) => old.includes(group) ? old.filter((g) => g !== group) : [...old, group])} className="inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-sm text-ink-secondary hover:bg-black/[0.04]">{collapsed.includes(group) ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}{group}</button>)}</div><label className="flex min-h-10 items-center gap-2 text-sm text-ink-secondary"><input type="checkbox" checked={all} onChange={(event) => setAll(event.target.checked)} />显示全部技能</label></div>
    {!shown.length ? <p className="py-10 text-sm text-ink-secondary">{skills.some((s) => s.relevant) ? '展开一个技能分组查看路线。' : '先分析目标 JD，路线图会展示相关技能和必要基础。也可以勾选“显示全部技能”浏览目录。'}</p> : <>
      <div className="hidden overflow-x-auto rounded-xl bg-[#FAFAFC] md:block" tabIndex={0} aria-label="可横向滚动的技能路线"><div className="relative" style={{ width, height }}>
        <svg className="pointer-events-none absolute inset-0" width={width} height={height} aria-hidden="true"><defs><marker id="growth-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#8C96A5" /></marker></defs>{positioned.flatMap((skill) => skill.dependencies.map((id) => {
          const dependency = positioned.find((s) => s.id === id)
          if (!dependency) return null
          const x1 = dependency.x + 144, y1 = dependency.y + 54, x2 = skill.x - 4, y2 = skill.y + 54
          return <path key={`${id}-${skill.id}`} d={`M${x1},${y1} C${x1 + 18},${y1} ${x2 - 18},${y2} ${x2},${y2}`} fill="none" stroke="#A3ADBC" strokeWidth="1.3" markerEnd="url(#growth-arrow)" />
        }))}</svg>
        {positioned.map((skill) => <button key={skill.id} type="button" aria-pressed={selected === skill.id} aria-label={`${skill.name}，${skill.level ? `等级 ${skill.level}` : '待验证'}，${SKILL_STATUS[skill.status]}${skill.reviewDue ? '，待复习' : ''}${skill.recommended ? '，建议下一步' : ''}`} onClick={() => choose(skill.id)} className={`absolute min-h-[108px] w-36 rounded-xl border p-3 text-left text-ink-body transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${selected === skill.id ? 'border-brand bg-brand-soft' : skill.recommended ? 'border-brand/40 bg-white hover:bg-brand-soft' : 'border-black/10 bg-white hover:bg-black/[0.03]'}`} style={{ left: skill.x, top: skill.y }}>{node(skill)}</button>)}
      </div></div>
      <div className="space-y-5 md:hidden">{groups.map((group) => {
        const items = shown.filter((s) => s.group === group)
        return items.length ? <section key={group}><h3 className="mb-2 text-sm font-medium text-ink-secondary">{group}</h3><div className="divide-y divide-black/[0.06]">{items.map((skill) => <button key={skill.id} type="button" onClick={() => choose(skill.id)} aria-pressed={selected === skill.id} className={`block min-h-24 w-full rounded-lg p-3 text-left ${selected === skill.id ? 'bg-brand-soft' : 'hover:bg-black/[0.03]'}`}>{node(skill)}{skill.dependencies.length > 0 && <span className="mt-2 block text-xs text-ink-secondary">前置：{skill.dependencies.map((id) => skills.find((s) => s.id === id)?.name).join('、')}</span>}</button>)}</div></section> : null
      })}</div>
      <p className="mt-3 text-xs leading-5 text-ink-secondary">箭头表示学习前置关系。等级来自证据；待复习表示需要再次回忆，时间经过不会自动降级。</p>
    </>}
  </section>
}
