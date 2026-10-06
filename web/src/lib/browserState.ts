export function readStored(key: string, session = false): string | null {
  try { return (session ? sessionStorage : localStorage).getItem(key) } catch { return null }
}
export function writeStored(key: string, value: string | null, session = false) {
  try {
    const store = session ? sessionStorage : localStorage
    if (value === null) store.removeItem(key)
    else store.setItem(key, value)
  } catch { /* Restricted or full storage must not prevent editing. */ }
}
export function safeJobsReturn(value: string | null): string {
  if (!value) return '/jobs'
  try {
    const url = new URL(value, 'http://career-radar.local')
    return url.origin === 'http://career-radar.local' && url.pathname === '/jobs'
      ? `${url.pathname}${url.search}` : '/jobs'
  } catch { return '/jobs' }
}
export function jobDetailHref(id: string, from: string) {
  return `/jobs/${encodeURIComponent(id)}?${new URLSearchParams({ from: safeJobsReturn(from) })}`
}
export function formatLocalTime(value: string | null | undefined): string {
  if (!value) return '尚无记录'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date)
}
