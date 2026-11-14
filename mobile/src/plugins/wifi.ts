export type WifiInfo = {
  ssid: string | null
  bssid: string | null
  available: boolean
  reason?: string
}

export interface WifiPlugin {
  getInfo(): Promise<WifiInfo>
}

export const wifiPlugin: WifiPlugin = {
  async getInfo() {
    return {
      ssid: null,
      bssid: null,
      available: false,
      reason: 'Native Wi-Fi information retrieval is not implemented.',
    }
  },
}
