import { vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

vi.mock('@capacitor/core', () => ({
  Capacitor: {
    getPlatform: vi.fn(() => 'web'),
    isPluginAvailable: vi.fn(() => false),
  },
}))
