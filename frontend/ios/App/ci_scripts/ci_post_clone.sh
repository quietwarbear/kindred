#!/bin/sh
set -e
brew install cocoapods
cd $CI_PRIMARY_REPOSITORY_PATH/frontend
npm install
npx cap sync ios
cd $CI_PRIMARY_REPOSITORY_PATH/frontend/ios/App
pod install
