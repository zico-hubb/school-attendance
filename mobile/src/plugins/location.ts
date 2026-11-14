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
}

export const locationPlugin: LocationPlugin = {
  async getCurrentLocation() {
    return {
      available: false,
      reason: 'Native location retrieval is not implemented.',
    }
  },
}
