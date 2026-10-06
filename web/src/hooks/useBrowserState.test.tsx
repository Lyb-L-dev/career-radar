import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation, useNavigate, useSearchParams } from 'react-router'
import { useLocalDraft, useUrlSearch } from './useBrowserState'

function SearchProbe() {
  const search = useUrlSearch()
  const location = useLocation()
  const navigate = useNavigate()
  const [, setParams] = useSearchParams()
  return <><input aria-label="search" {...search.bind} /><output>{location.search}</output><button onClick={() => navigate(-1)}>Back</button><button onClick={() => setParams(old => { const next = new URLSearchParams(old); next.set('category', 'review'); return next })}>Filter</button></>
}
function DraftProbe() {
  const draft = useLocalDraft('test-draft', { code: '', explanation: '' })
  return <input aria-label="draft" value={draft.value.code} onChange={event => draft.update({ code: event.target.value })} />
}
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); localStorage.clear() })

describe('URL search and draft recovery', () => {
  it('waits for Chinese composition and merges a concurrent filter change', async () => {
    vi.useFakeTimers()
    render(<MemoryRouter initialEntries={['/jobs?source=boss']}><SearchProbe /></MemoryRouter>)
    const input = screen.getByLabelText('search')
    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '智能' } })
    await act(() => vi.advanceTimersByTimeAsync(400))
    expect(screen.getByRole('status').textContent).not.toContain('q=')
    fireEvent.compositionEnd(input)
    fireEvent.click(screen.getByText('Filter'))
    await act(() => vi.advanceTimersByTimeAsync(300))
    const params = new URLSearchParams(screen.getByRole('status').textContent!)
    expect(params.get('q')).toBe('智能')
    expect(params.get('category')).toBe('review')
  })
  it('restores a previous URL rather than replacing it with the last typed value', () => {
    render(<MemoryRouter initialEntries={['/jobs?q=HTTP', '/jobs?q=Agent']} initialIndex={1}><SearchProbe /></MemoryRouter>)
    fireEvent.click(screen.getByText('Back'))
    expect(screen.getByLabelText('search')).toHaveValue('HTTP')
  })
  it('restores project text after remount and tolerates unavailable storage', () => {
    const view = render(<DraftProbe />)
    fireEvent.change(screen.getByLabelText('draft'), { target: { value: 'submitted project code' } })
    view.unmount()
    render(<DraftProbe />)
    expect(screen.getByLabelText('draft')).toHaveValue('submitted project code')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    fireEvent.change(screen.getByLabelText('draft'), { target: { value: 'still editable' } })
    expect(screen.getByLabelText('draft')).toHaveValue('still editable')
  })
})
