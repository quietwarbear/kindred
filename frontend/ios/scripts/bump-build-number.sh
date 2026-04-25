#!/bin/bash
#
# Auto-increment iOS CFBundleVersion (CURRENT_PROJECT_VERSION) after a successful Release build.
# Mirrors the Android version.properties auto-increment in frontend/android/app/build.gradle.
#
# Wired in as a Run Script Build Phase on the App target. Only fires for Release;
# Debug/Simulator builds do NOT bump, so day-to-day dev work doesn't burn through numbers.
#
# Uses Apple's `agvtool`, which handles pbxproj file locking safely during a build.
# Requires `VERSIONING_SYSTEM = "apple-generic"` in the project's build settings (already set).

set -e

if [ "$CONFIGURATION" != "Release" ]; then
    echo "==> Skipping build number bump (CONFIGURATION=$CONFIGURATION, not Release)"
    exit 0
fi

# agvtool runs from the directory containing the .xcodeproj
cd "$PROJECT_DIR"

CURRENT=$(xcrun agvtool what-version -terse)
xcrun agvtool next-version -all >/dev/null
NEXT=$(xcrun agvtool what-version -terse)

echo "==> CFBundleVersion bumped: $CURRENT -> $NEXT (next Release archive will use $NEXT)"
