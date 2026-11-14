import { Capacitor } from '@capacitor/core'
import { getRuntimePlatform, type RuntimePlatform } from './platform'

export type NativeCapabilities = {
  platform: RuntimePlatform
  nativeVerification: {
    available: boolean
    reason?: string
  }
}

export function detectCapabilities(
  platform: RuntimePlatform,
  isPluginAvailable: (name: string) => boolean,
): NativeCapabilities {
  const nativePlatform = platform === 'android' || platform === 'ios'
  const pluginAvailable = isPluginAvailable('SchoolAttendanceDeviceVerification')
  return {
    platform,
    nativeVerification: {
      available: nativePlatform && pluginAvailable,
      ...(!nativePlatform
        ? { reason: 'Native device verification is unavailable in browser development.' }
        : !pluginAvailable
          ? { reason: 'Native device verification has not been implemented for this platform.' }
          : {}),
    },
  }
}

export function getPlatformCapabilities(): NativeCapabilities {
  return detectCapabilities(getRuntimePlatform(), (pluginName) =>
    Capacitor.isPluginAvailable(pluginName),
  )
}
