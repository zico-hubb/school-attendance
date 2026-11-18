import { vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

vi.mock('@capacitor/core', () => ({
  registerPlugin: vi.fn(() => ({
    registerPublicKey: vi.fn(async () => ({ available: false, reason: 'Unavailable in test.' })),
    signChallenge: vi.fn(async () => ({ available: false, reason: 'Unavailable in test.' })),
  })),
  Capacitor: {
    getPlatform: vi.fn(() => 'web'),
    isPluginAvailable: vi.fn(() => false),
  },
}))
