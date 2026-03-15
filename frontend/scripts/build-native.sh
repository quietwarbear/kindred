#!/bin/bash
# Kindred — Build and sync for Capacitor native platforms
set -e

echo "=== Kindred Native Build ==="
echo "Bundle ID: com.ubuntumarket.kindred"
echo ""

cd /app/frontend

# Step 1: Build the React app
echo "[1/3] Building React app..."
GENERATE_SOURCEMAP=false yarn build

# Step 2: Sync to native platforms
echo "[2/3] Syncing to Capacitor..."
npx cap sync

echo "[3/3] Done!"
echo ""
echo "Next steps:"
echo "  iOS:     npx cap open ios     (requires Xcode on macOS)"
echo "  Android: npx cap open android (requires Android Studio)"
echo ""
echo "To run on device:"
echo "  npx cap run ios"
echo "  npx cap run android"
