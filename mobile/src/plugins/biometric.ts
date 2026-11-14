export type BiometricCapability = {
  available: boolean
  enrolled: boolean
  reason?: string
}

export type BiometricAuthenticationResult =
  | { available: true; authenticated: boolean }
  | { available: false; reason: string }

export interface BiometricPlugin {
  getCapability(): Promise<BiometricCapability>
  authenticate(reason: string): Promise<BiometricAuthenticationResult>
}

const unsupportedReason = 'Native biometric support is not implemented.'

export const biometricPlugin: BiometricPlugin = {
  async getCapability() {
    return { available: false, enrolled: false, reason: unsupportedReason }
  },
  async authenticate() {
    return { available: false, reason: unsupportedReason }
  },
}
