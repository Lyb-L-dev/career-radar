import { useState } from 'react'
import type { CompanyType, IndustryCategory, MonitorMode } from '@/types'

export interface CompanyMonitorFormValue {
  website: string
  careersUrl: string
  companyType: CompanyType
  industryCategory: IndustryCategory
  monitorMode: MonitorMode
  maxPages: string
  enabled: boolean
  note: string
}

export const DEFAULT_COMPANY_MONITOR_FORM: CompanyMonitorFormValue = {
  website: '',
  careersUrl: '',
  companyType: 'private',
  industryCategory: 'other',
  monitorMode: 'jobs',
  maxPages: '20',
  enabled: true,
  note: '',
}

export function useCompanyMonitorForm(initial: Partial<CompanyMonitorFormValue> = {}) {
  const initialValue = { ...DEFAULT_COMPANY_MONITOR_FORM, ...initial }
  const [value, setValue] = useState<CompanyMonitorFormValue>(initialValue)

  const update = <K extends keyof CompanyMonitorFormValue>(
    key: K,
    next: CompanyMonitorFormValue[K],
  ) => {
    setValue((current) => ({ ...current, [key]: next }))
  }

  return {
    value,
    update,
    reset: () => setValue(initialValue),
  }
}
