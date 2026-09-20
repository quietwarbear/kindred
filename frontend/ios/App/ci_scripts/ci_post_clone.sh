#!/bin/sh
set -e

# Install Node.js via nvm (Xcode Cloud doesn't include it by default)
export NVM_DIR="$HOME/.nvm"
if [ ! -d "$NVM_DIR" ]; then
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
fi
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 22
nvm use 22

cd $CI_PRIMARY_REPOSITORY_PATH/frontend
# Reproduce the committed dependency graph. `npm install` previously floated
# @sentry/capacitor to 4.4.0, whose npm tarball omitted the CocoaPods podspec.
npm ci --legacy-peer-deps

if [ ! -f node_modules/@sentry/capacitor/SentryCapacitor.podspec ]; then
  echo "error: @sentry/capacitor is missing SentryCapacitor.podspec" >&2
  exit 1
fi

GENERATE_SOURCEMAP=false CI=false npm run build
npx cap sync ios
cd $CI_PRIMARY_REPOSITORY_PATH/frontend/ios/App
pod install
