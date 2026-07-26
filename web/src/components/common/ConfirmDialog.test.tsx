import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('does not invoke a disabled destructive confirmation', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        onOpenChange={() => undefined}
        title="删除企业？"
        description="至少保留一家企业。"
        confirmLabel="确认删除"
        destructive
        confirmDisabled
        onConfirm={onConfirm}
      />,
    )

    const button = screen.getByRole('button', { name: '确认删除' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
