import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import {
  CompanyMonitorFields,
} from './CompanyMonitorFields'
import {
  DEFAULT_COMPANY_MONITOR_FORM,
} from '@/hooks/useCompanyMonitorForm'
import type { CompanyMonitorFormValue } from '@/hooks/useCompanyMonitorForm'

function Harness() {
  const [value, setValue] = useState(DEFAULT_COMPANY_MONITOR_FORM)
  const update = <K extends keyof CompanyMonitorFormValue>(
    key: K,
    next: CompanyMonitorFormValue[K],
  ) => setValue((current) => ({ ...current, [key]: next }))

  return <CompanyMonitorFields value={value} onChange={update} idPrefix="test-company" />
}

describe('CompanyMonitorFields', () => {
  it('shares controlled website and page-limit fields across dialogs', () => {
    render(<Harness />)

    const website = screen.getByLabelText('企业官网 *')
    fireEvent.change(website, { target: { value: 'https://example.com' } })
    expect(website).toHaveValue('https://example.com')

    const maxPages = screen.getByLabelText('最大扫描页面数')
    expect(maxPages).toHaveAttribute('max', '5000')
    fireEvent.change(maxPages, { target: { value: '120' } })
    expect(maxPages).toHaveValue(120)
  })
})
