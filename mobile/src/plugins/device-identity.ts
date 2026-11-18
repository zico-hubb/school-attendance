import { registerPlugin } from '@capacitor/core'

export type PublicKeyRegistration = {
  keyId: string
  publicKey: string
  algorithm: string
}

export type DeviceIdentityResult<T> =
  | { available: true; value: T }
  | { available: false; reason: string }

export interface DeviceIdentityPlugin {
  registerPublicKey(): Promise<DeviceIdentityResult<PublicKeyRegistration>>
  signChallenge(challenge: string): Promise<DeviceIdentityResult<{ signature: string }>>
}

const nativePlugin = registerPlugin<DeviceIdentityPlugin>('SchoolAttendanceDeviceIdentity')
const unsupportedReason =
  'Native device identity is unavailable in browser development.'

export const deviceIdentityPlugin: DeviceIdentityPlugin = {
  async registerPublicKey() {
    if (nativePlugin.registerPublicKey) {
      try { return await nativePlugin.registerPublicKey() } catch (error) {
        return { available: false, reason: error instanceof Error ? error.message : 'Device key generation failed.' }
      }
    }
    return { available: false, reason: unsupportedReason }
  },
  async signChallenge(challenge: string) {
    if (nativePlugin.signChallenge) {
      try { return await nativePlugin.signChallenge({ challenge } as never) } catch (error) {
        return { available: false, reason: error instanceof Error ? error.message : 'Challenge signing failed.' }
      }
    }
    return { available: false, reason: unsupportedReason }
  },
}
