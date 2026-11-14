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

const unsupportedReason =
  'Hardware-backed device identity is not implemented; no browser cryptography is used as a substitute.'

export const deviceIdentityPlugin: DeviceIdentityPlugin = {
  async registerPublicKey() {
    return { available: false, reason: unsupportedReason }
  },
  async signChallenge() {
    return { available: false, reason: unsupportedReason }
  },
}
