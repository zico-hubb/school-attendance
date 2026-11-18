export type WifiInfo = {
  ssid: string | null
  bssid: string | null
  available: boolean
  reason?: string
}

export interface WifiPlugin {
  getInfo(): Promise<WifiInfo>
}

import { registerPlugin } from '@capacitor/core'
const nativePlugin = registerPlugin<WifiPlugin>('SchoolAttendanceWifi')

export const wifiPlugin: WifiPlugin = {
  async getInfo() {
    if (nativePlugin.getInfo) {
      try { return await nativePlugin.getInfo() } catch (error) {
        return { ssid: null, bssid: null, available: false, reason: error instanceof Error ? error.message : 'Wi-Fi information failed.' }
      }
    }
    return {
      ssid: null,
      bssid: null,
      available: false,
      reason: 'Native Wi-Fi information retrieval is not implemented.',
    }
  },
}
