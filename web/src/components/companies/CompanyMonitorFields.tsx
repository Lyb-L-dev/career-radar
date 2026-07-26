import { EnumSelect } from '@/components/common/EnumSelect'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  COMPANY_TYPE_LABEL,
  INDUSTRY_CATEGORY_LABEL,
  MONITOR_MODE_LABEL,
} from '@/types'
import type { CompanyMonitorFormValue } from '@/hooks/useCompanyMonitorForm'

export function CompanyMonitorFields({
  value,
  onChange,
  idPrefix,
  enabledTitle = '启用监控',
  enabledDescription = '关闭后该企业不参与每日扫描',
  noteLabel = '企业备注',
  notePlaceholder = '可选，例如重点关注的产品线',
}: {
  value: CompanyMonitorFormValue
  onChange: <K extends keyof CompanyMonitorFormValue>(
    key: K,
    next: CompanyMonitorFormValue[K],
  ) => void
  idPrefix: string
  enabledTitle?: string
  enabledDescription?: string
  noteLabel?: string
  notePlaceholder?: string
}) {
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor={`${idPrefix}-website`}>企业官网 *</Label>
          <Input
            id={`${idPrefix}-website`}
            value={value.website}
            onChange={(event) => onChange('website', event.target.value)}
            placeholder="https://company.example.com"
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor={`${idPrefix}-careers`}>官方招聘入口</Label>
          <Input
            id={`${idPrefix}-careers`}
            value={value.careersUrl}
            onChange={(event) => onChange('careersUrl', event.target.value)}
            placeholder="可留空，由首页发现招聘入口"
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5">
          <Label>公司类型</Label>
          <EnumSelect
            value={value.companyType}
            labels={COMPANY_TYPE_LABEL}
            onValueChange={(next) => onChange('companyType', next)}
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5">
          <Label>行业分类</Label>
          <EnumSelect
            value={value.industryCategory}
            labels={INDUSTRY_CATEGORY_LABEL}
            onValueChange={(next) => onChange('industryCategory', next)}
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5">
          <Label>监控内容</Label>
          <EnumSelect
            value={value.monitorMode}
            labels={MONITOR_MODE_LABEL}
            onValueChange={(next) => onChange('monitorMode', next)}
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-pages`}>最大扫描页面数</Label>
          <Input
            id={`${idPrefix}-pages`}
            type="number"
            min={1}
            max={5000}
            value={value.maxPages}
            onChange={(event) => onChange('maxPages', event.target.value)}
            className="rounded-lg"
          />
        </div>
      </div>
      <div className="flex items-center justify-between rounded-lg bg-surface-subtle px-3.5 py-3">
        <div>
          <p className="text-[14px] font-medium text-ink">{enabledTitle}</p>
          <p className="text-[12px] text-ink-tertiary">{enabledDescription}</p>
        </div>
        <Switch checked={value.enabled} onCheckedChange={(next) => onChange('enabled', next)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${idPrefix}-note`}>{noteLabel}</Label>
        <Textarea
          id={`${idPrefix}-note`}
          value={value.note}
          onChange={(event) => onChange('note', event.target.value)}
          placeholder={notePlaceholder}
          rows={3}
          className="rounded-lg"
        />
      </div>
    </>
  )
}
