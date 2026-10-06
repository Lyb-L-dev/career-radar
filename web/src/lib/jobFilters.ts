import type { JobTab } from '@/types'

export const ALL_FILTER_VALUE = '__all__'
export const SAVED_JOB_FILTERS_KEY = 'career-radar.saved-job-filters.v1'

const JOB_TABS: JobTab[] = ['recommended', 'unreviewed', 'notice', 'new', 'updated', 'all', 'favorite']

export interface JobFilterValues {
  tab: JobTab
  keyword: string
  companyId: string
  companyType: string
  industryCategory: string
  province: string
  city: string
  jobType: string
  ability: string
  maxDifficulty: string
  eligibility: string
  sort: string
}

export const DEFAULT_JOB_FILTER_VALUES: JobFilterValues = {
  tab: 'all',
  keyword: '',
  companyId: ALL_FILTER_VALUE,
  companyType: ALL_FILTER_VALUE,
  industryCategory: ALL_FILTER_VALUE,
  province: ALL_FILTER_VALUE,
  city: ALL_FILTER_VALUE,
  jobType: ALL_FILTER_VALUE,
  ability: ALL_FILTER_VALUE,
  maxDifficulty: ALL_FILTER_VALUE,
  eligibility: 'available',
  sort: 'priority',
}

const PARAM_KEYS: Record<Exclude<keyof JobFilterValues, 'tab'>, string> = {
  keyword: 'q',
  companyId: 'company',
  companyType: 'companyType',
  industryCategory: 'industry',
  province: 'province',
  city: 'city',
  jobType: 'type',
  ability: 'ability',
  maxDifficulty: 'difficulty',
  eligibility: 'eligibility',
  sort: 'sort',
}

export function jobFilterValuesFromParams(params: URLSearchParams): JobFilterValues {
  const tabParam = params.get('tab') as JobTab | null
  const values = { ...DEFAULT_JOB_FILTER_VALUES }
  values.tab = tabParam && JOB_TABS.includes(tabParam) ? tabParam : values.tab
  for (const [field, key] of Object.entries(PARAM_KEYS)) {
    const value = params.get(key)
    if (value) values[field as keyof typeof PARAM_KEYS] = value
  }
  if (![ALL_FILTER_VALUE, 'available', 'eligible', 'review', 'ineligible'].includes(values.eligibility)) values.eligibility = DEFAULT_JOB_FILTER_VALUES.eligibility
  if (!['priority', 'updated'].includes(values.sort)) values.sort = DEFAULT_JOB_FILTER_VALUES.sort
  return values
}

export function jobFilterValuesToParams(values: JobFilterValues): URLSearchParams {
  const params = new URLSearchParams()
  params.set('tab', values.tab)
  for (const [field, key] of Object.entries(PARAM_KEYS)) {
    const value = values[field as keyof typeof PARAM_KEYS]
    if (value && value !== ALL_FILTER_VALUE) params.set(key, value)
  }
  return params
}

export function hasFilterParams(params: URLSearchParams): boolean {
  return Object.values(PARAM_KEYS).some((key) => params.has(key))
}

export function loadSavedJobFilters(): JobFilterValues | null {
  try {
    const raw = window.localStorage.getItem(SAVED_JOB_FILTERS_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<JobFilterValues>
    return {
      ...DEFAULT_JOB_FILTER_VALUES,
      ...Object.fromEntries(
        Object.keys(DEFAULT_JOB_FILTER_VALUES)
          .filter((key) => typeof parsed[key as keyof JobFilterValues] === 'string')
          .map((key) => [key, parsed[key as keyof JobFilterValues]]),
      ),
      tab: JOB_TABS.includes(parsed.tab as JobTab)
        ? (parsed.tab as JobTab)
        : DEFAULT_JOB_FILTER_VALUES.tab,
    }
  } catch {
    return null
  }
}

export function saveJobFilters(values: JobFilterValues): void {
  window.localStorage.setItem(SAVED_JOB_FILTERS_KEY, JSON.stringify(values))
}
