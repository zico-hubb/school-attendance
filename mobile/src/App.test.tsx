import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { detectCapabilities } from './platform/capabilities'
import { getRuntimePlatform } from './platform/platform'
import { biometricPlugin } from './plugins/biometric'
import { deviceIdentityPlugin } from './plugins/device-identity'
import { locationPlugin } from './plugins/location'
import { wifiPlugin } from './plugins/wifi'

describe('staff mobile application', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders the staff application without claiming unfinished features', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'School Attendance' })).toBeInTheDocument()
    expect(screen.getByText(/sign-in and attendance workflows are not available yet/i)).toBeInTheDocument()
    expect(screen.getByTestId('platform-name')).toHaveTextContent('Platform: web')
    expect(screen.getByTestId('capability-status')).toHaveTextContent('Native verification: not available')
  })

  it('reports the web platform and unavailable native verification', () => {
    expect(getRuntimePlatform()).toBe('web')
    const result = detectCapabilities('web', () => true)

    expect(result.platform).toBe('web')
    expect(result.nativeVerification).toEqual({
      available: false,
      reason: 'Native device verification is unavailable in browser development.',
    })
  })

  it('does not report missing native plugins as available on a native platform', () => {
    const result = detectCapabilities('android', () => false)

    expect(result.nativeVerification).toEqual({
      available: false,
      reason: 'Native device verification has not been implemented for this platform.',
    })
  })

  it('returns explicit unavailable results from every native contract', async () => {
    await expect(wifiPlugin.getInfo()).resolves.toMatchObject({ available: false, bssid: null })
    await expect(locationPlugin.getCurrentLocation()).resolves.toMatchObject({ available: false })
    await expect(deviceIdentityPlugin.registerPublicKey()).resolves.toMatchObject({ available: false })
    await expect(deviceIdentityPlugin.signChallenge('challenge')).resolves.toMatchObject({
      available: false,
    })
    await expect(biometricPlugin.getCapability()).resolves.toMatchObject({
      available: false,
      enrolled: false,
    })
    await expect(biometricPlugin.authenticate('test')).resolves.toMatchObject({
      available: false,
    })
  })
})
