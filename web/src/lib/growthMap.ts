import type { GrowthSkill } from '@/services/growth'

export const SKILL_STATUS = { unverified: '待验证', developing: '正在建立证据', mastered: '已有掌握证据', needs_practice: '需要巩固' }
export const POINT_STATUS = { unassessed: '尚未测评', independent: '独立通过', needs_hint: '需要提示', not_learned: '尚未学习' }

export function layoutGrowthSkills(skills: GrowthSkill[]) {
  const mapping = new Map(skills.map((skill) => [skill.id, skill]))
  const depths = new Map<string, number>()
  function depth(id: string, trail: Set<string> = new Set()): number {
    if (depths.has(id)) return depths.get(id)!
    if (trail.has(id)) return 0
    const dependencies = mapping.get(id)?.dependencies.filter((d) => mapping.has(d)) ?? []
    const value = dependencies.length ? 1 + Math.max(...dependencies.map((d) => depth(d, new Set([...trail, id])))) : 0
    depths.set(id, value)
    return value
  }
  const rows = new Map<number, number>()
  return skills.map((skill) => {
    const column = depth(skill.id)
    const row = rows.get(column) ?? 0
    rows.set(column, row + 1)
    return { ...skill, x: 20 + column * 164, y: 20 + row * 132 }
  })
}
