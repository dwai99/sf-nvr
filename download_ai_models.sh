#!/bin/bash
# Download AI detection models for SF-NVR
set -e

echo "📥 Downloading AI detection models..."
echo ""

# Create models directory
mkdir -p models
cd models

# Download MobileNet-SSD model files from reliable sources
echo "Downloading MobileNetSSD config..."
curl -L -o MobileNetSSD_deploy.prototxt \
  "https://gist.githubusercontent.com/dkurt/54a8e8b51beb3bd3f770b79e56927bd7/raw/2a20064a9d33b893dd95d2567da126d0ecd03e49/MobileNetSSD_deploy.prototxt"

echo "Downloading MobileNetSSD weights (23MB)..."
curl -L -o MobileNetSSD_deploy.caffemodel \
  "https://github.com/chuanqi305/MobileNet-SSD/raw/f5d072ccc7e3dcddaa830e9805da4bf1000b2836/MobileNetSSD_deploy.caffemodel"

# Verify files were downloaded
if [ ! -f "MobileNetSSD_deploy.prototxt" ] || [ ! -s "MobileNetSSD_deploy.prototxt" ]; then
    echo "❌ Failed to download prototxt file"
    exit 1
fi

if [ ! -f "MobileNetSSD_deploy.caffemodel" ] || [ ! -s "MobileNetSSD_deploy.caffemodel" ]; then
    echo "❌ Failed to download caffemodel file"
    exit 1
fi

echo ""
echo "✅ Model files downloaded successfully!"
echo ""
echo "Files saved to:"
ls -lh MobileNetSSD_deploy.*
echo ""
echo "You can now start the NVR with AI detection enabled."
