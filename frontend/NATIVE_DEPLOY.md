# Kindred — Native App Deployment Guide

## App Configuration
- **Bundle ID**: `com.ubuntumarket.kindred`
- **App Name**: Kindred
- **Framework**: React + Capacitor 6
- **Platforms**: iOS (App Store), Android (Google Play)

## Prerequisites

### macOS (required for iOS)
- Xcode 15+ (from Mac App Store)
- CocoaPods: `sudo gem install cocoapods`
- Apple Developer account ($99/year)

### Android
- Android Studio (any OS)
- Java 17+
- Google Play Developer account ($25 one-time)

## First-Time Setup

```bash
cd /app/frontend

# Build the React app
GENERATE_SOURCEMAP=false yarn build

# Add native platforms
npx cap add ios
npx cap add android

# Sync web assets to native projects
npx cap sync
```

## Development Workflow

```bash
# After making web changes:
yarn build && npx cap sync

# Open in IDE:
npx cap open ios       # Opens Xcode
npx cap open android   # Opens Android Studio

# Live reload during development:
npx cap run ios --livereload --external
npx cap run android --livereload --external
```

## iOS — App Store Submission

### 1. Configure Xcode Project
- Open `ios/App/App.xcworkspace` in Xcode
- Set **Team** to your Apple Developer account
- Set **Bundle Identifier** to `com.ubuntumarket.kindred`
- Set **Display Name** to `Kindred`
- Add required capabilities:
  - Push Notifications
  - Camera Usage Description: "Kindred uses your camera to capture memories"
  - Microphone Usage Description: "Kindred uses your microphone for voice notes"
  - Photo Library Usage Description: "Kindred accesses photos for your Memory Vault"

### 2. Add App Icons
- In Xcode, go to Assets.xcassets → AppIcon
- Drag in the generated icons (use an icon generator like appicon.co)

### 3. Build & Archive
- Select "Any iOS Device" as target
- Product → Archive
- Distribute App → App Store Connect
- Upload

### 4. App Store Connect
- Go to appstoreconnect.apple.com
- Create new app with bundle ID `com.ubuntumarket.kindred`
- Fill in app description, screenshots, privacy policy
- Submit for review

## Android — Google Play Submission

### 1. Configure Android Studio
- Open `android/` folder in Android Studio
- Verify `applicationId` is `com.ubuntumarket.kindred` in `app/build.gradle`

### 2. Generate Signed APK/AAB
```bash
cd android
./gradlew bundleRelease
```
- Sign with your upload key
- Output: `app/build/outputs/bundle/release/app-release.aab`

### 3. Google Play Console
- Create new app
- Upload AAB
- Fill in store listing, screenshots, privacy policy
- Submit for review

## RevenueCat Mobile Setup

### iOS
1. In RevenueCat dashboard, add iOS app with bundle ID `com.ubuntumarket.kindred`
2. Add App Store Connect API key in RevenueCat
3. Create Products matching entitlement IDs: `seedling`, `sapling`, `oak`, `redwood`, `elder_grove`
4. The Kindred backend webhook is already configured at:
   `https://your-domain.com/api/revenuecat/webhook`

### Android
1. Add Android app with package name `com.ubuntumarket.kindred`
2. Add Google Play service account JSON in RevenueCat
3. Create matching products in Google Play Console

## Native Plugin Permissions (Info.plist / AndroidManifest.xml)

These are added automatically by Capacitor, but verify:

### iOS (ios/App/App/Info.plist)
```xml
<key>NSCameraUsageDescription</key>
<string>Kindred uses your camera to capture memories for your community</string>
<key>NSMicrophoneUsageDescription</key>
<string>Kindred uses your microphone for voice notes and reflections</string>
<key>NSPhotoLibraryUsageDescription</key>
<string>Kindred accesses your photos for the Memory Vault</string>
```

### Android (android/app/src/main/AndroidManifest.xml)
```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
```

## Environment

The Capacitor app connects to the same backend API. For production:
1. Update `REACT_APP_BACKEND_URL` in `.env` to your production URL
2. Rebuild: `yarn build && npx cap sync`

For development with live reload:
```bash
# Set your local IP
REACT_APP_BACKEND_URL=http://192.168.1.x:8001 npx cap run ios --livereload --external
```
