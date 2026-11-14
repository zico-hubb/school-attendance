# Mobile platform support

## Implemented

- A shared React, TypeScript, and Vite application.
- Capacitor configuration with app id `ke.schoolattendance.staff`, app name `School Attendance Staff`, and web output directory `dist`.
- Capacitor core, CLI, Android, and iOS npm dependencies.
- An Android native project generated with the official Capacitor CLI and synchronized with the web assets.
- Browser platform detection and explicit unavailable native plugin contracts.

## Not implemented or verified

- The Android project has not been built or tested because this Dell has no Android Studio/SDK; continue on the HP after installing them.
- An iOS native project has not been generated. iOS project creation/build/signing is deferred because those workflows require macOS/Xcode, which is not available on Windows.
- There are no Kotlin or Swift plugins, native permissions, keystore/secure-enclave code, Wi-Fi access, or native location access.
- Browser tests and builds do not validate native platform functionality.

## Continue on the HP (Windows)

Install/configure Android Studio and the Android SDK, then from `mobile/` run `npm run cap -- sync android` and build/run with Android Studio or `npm run cap -- run android`. Implement and test Kotlin plugins on an emulator and physical device.

## Continue on a Mac

From `mobile/`, run `npm run cap -- add ios` if the project is not already present, then `npm run cap -- sync ios`. Xcode/macOS is required for project generation/build/signing workflows, simulator and device testing, Swift plugins, and distribution. Follow current Apple permission and Wi-Fi privacy requirements.
