import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

describe('administration application', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders the administration workspace and reports an unavailable API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    render(<App />)

    expect(screen.getByRole('heading', { name: 'Administration' })).toBeInTheDocument()
    expect(screen.getByText(/workspace is ready/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText(/backend is unavailable/i)).toBeInTheDocument()
    })
  })

  it('renders the not-found route', () => {
    window.history.pushState({}, '', '/unknown')
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
    window.history.pushState({}, '', '/')
  })
})
