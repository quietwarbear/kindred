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
npm install --legacy-peer-deps
GENERATE_SOURCEMAP=false CI=false npm run build
npx cap sync ios
cd $CI_PRIMARY_REPOSITORY_PATH/frontend/ios/App
pod install
