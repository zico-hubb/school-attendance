import { Capacitor } from '@capacitor/core'

export type RuntimePlatform = 'android' | 'ios' | 'web' | 'other'

export function getRuntimePlatform(): RuntimePlatform {
  const platform = Capacitor.getPlatform()
  if (platform === 'android' || platform === 'ios' || platform === 'web') {
    return platform
  }
  return 'other'
}
