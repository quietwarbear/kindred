#!/bin/bash
# Auto-increment build number on archive

INFOPLIST="${PROJECT_DIR}/App/Info.plist"

if [ "${CONFIGURATION}" = "Release" ]; then
    buildNumber=$(/usr/libexec/PlistBuddy -c "Print CFBundleVersion" "$INFOPLIST")
    buildNumber=$((buildNumber + 1))
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $buildNumber" "$INFOPLIST"
    echo "Bumped build number to $buildNumber"
fi
