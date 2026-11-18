export type LocationInfo = {
  latitude: number
  longitude: number
  accuracyMeters: number
  timestamp: string
}

export type LocationResult =
  | { available: true; location: LocationInfo }
  | { available: false; reason: string }

export interface LocationPlugin {
  getCurrentLocation(): Promise<LocationResult>
  requestPermissions(): Promise<{ granted: boolean; reason?: string }>
}

import { registerPlugin } from '@capacitor/core'
const nativePlugin = registerPlugin<LocationPlugin>('SchoolAttendanceLocation')

export const locationPlugin: LocationPlugin = {
  async requestPermissions() {
    if (nativePlugin.requestPermissions) {
      try {
        const result = await nativePlugin.requestPermissions()
        return { granted: Boolean((result as unknown as { granted?: boolean }).granted) }
      } catch (error) {
        return { granted: false, reason: error instanceof Error ? error.message : 'Location permission request failed.' }
      }
    }
    return { granted: false, reason: 'Native location permission handling is unavailable in browser development.' }
  },
  async getCurrentLocation() {
    if (nativePlugin.getCurrentLocation) {
      try { return await nativePlugin.getCurrentLocation() } catch (error) {
        return { available: false, reason: error instanceof Error ? error.message : 'Location retrieval failed.' }
      }
    }
    return {
      available: false,
      reason: 'Native location retrieval is not implemented.',
    }
  },
}
