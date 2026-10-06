import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, CompositionEvent } from 'react'
import { useLocation, useSearchParams } from 'react-router'
import { readStored, writeStored } from '@/lib/browserState'

export function useUrlSearch(key = 'q') {
  const [params, setParams] = useSearchParams()
  const urlValue = params.get(key) ?? ''
  const source = params.get('source')
  const [draft, setDraft] = useState({ source, urlValue, value: urlValue })
  if (draft.source !== source || draft.urlValue !== urlValue) setDraft({ source, urlValue, value: urlValue })
  const value = draft.source === source && draft.urlValue === urlValue ? draft.value : urlValue
  const composing = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const setter = useRef(setParams)
  useEffect(() => { setter.current = setParams }, [setParams])
  useEffect(() => { clearTimeout(timer.current) }, [urlValue, source])
  useEffect(() => () => clearTimeout(timer.current), [])
  function edit(next: string) {
    setDraft({ source, urlValue, value: next })
    clearTimeout(timer.current)
    if (composing.current) return
    timer.current = setTimeout(() => setter.current((old) => {
      const updated = new URLSearchParams(old)
      if (next.trim()) updated.set(key, next)
      else updated.delete(key)
      updated.delete('shown')
      return updated
    }, { replace: true }), 300)
  }
  return { value, edit, bind: {
    value,
    onChange: (event: ChangeEvent<HTMLInputElement>) => edit(event.target.value),
    onCompositionStart: () => { composing.current = true; clearTimeout(timer.current) },
    onCompositionEnd: (event: CompositionEvent<HTMLInputElement>) => { composing.current = false; edit(event.currentTarget.value) },
  } }
}

export function useLocalDraft<T extends Record<string, string>>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const saved = JSON.parse(readStored(key) ?? '{}') as Record<string, unknown>
      return Object.fromEntries(Object.entries(initial).map(([field, fallback]) => [field,
        saved && typeof saved[field] === 'string' ? saved[field] : fallback])) as T
    } catch { return initial }
  })
  function update(patch: Partial<T>) {
    const next = { ...value, ...patch }
    setValue(next)
    writeStored(key, JSON.stringify(next))
  }
  return { value, update, clear: () => writeStored(key, null) }
}

export function useListScroll(ready: boolean) {
  const location = useLocation()
  const key = `career-radar.scroll:${location.pathname}${location.search}`
  useEffect(() => {
    const remember = () => writeStored(key, String(window.scrollY), true)
    window.addEventListener('scroll', remember, { passive: true })
    return () => window.removeEventListener('scroll', remember)
  }, [key])
  useEffect(() => {
    if (!ready) return
    const saved = readStored(key, true)
    if (saved === null) return
    const position = Number(saved)
    const frame = requestAnimationFrame(() => window.scrollTo({ top: Number.isFinite(position) ? position : 0, behavior: 'instant' }))
    return () => cancelAnimationFrame(frame)
  }, [key, ready])
}
