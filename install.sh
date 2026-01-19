#!/bin/bash
# Quick install script - creates venv and installs everything correctly

set -e

echo "======================================"
echo "  SF-NVR Installation"
echo "======================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found"
    exit 1
fi

echo "Python: $(python3 --version)"
echo ""

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Failed to activate venv"
    exit 1
fi

echo "✓ Virtual environment activated: $VIRTUAL_ENV"

# Upgrade pip
echo ""
echo "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
python3 -m pip install -r requirements.txt

# Verify ONVIF
echo ""
echo "Verifying ONVIF installation..."
python3 << 'EOF'
from pathlib import Path
import onvif

onvif_path = Path(onvif.__file__).parent
wsdl_path = onvif_path / 'wsdl'

print(f"ONVIF location: {onvif_path}")
print(f"WSDL exists: {wsdl_path.exists()}")

if wsdl_path.exists():
    import os
    wsdl_files = [f for f in os.listdir(wsdl_path) if f.endswith('.wsdl')]
    print(f"WSDL files: {len(wsdl_files)}")
    if 'devicemgmt.wsdl' in wsdl_files:
        print("✓ ONVIF installation OK!")
    else:
        print("⚠ devicemgmt.wsdl missing")
        exit(1)
else:
    print("❌ WSDL directory not found")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ ONVIF installation problem detected"
    echo ""
    echo "The git version failed. Trying alternative fix..."

    # Download WSDL files manually
    echo "Downloading WSDL files..."
    mkdir -p /tmp/onvif-wsdl
    cd /tmp/onvif-wsdl

    curl -sL https://github.com/FalkTannhaeuser/python-onvif-zeep/archive/refs/heads/master.zip -o master.zip
    unzip -q master.zip

    ONVIF_DIR=$(python3 -c "import onvif; from pathlib import Path; print(Path(onvif.__file__).parent)")
    cp -r python-onvif-zeep-master/wsdl "$ONVIF_DIR/"

    echo "✓ WSDL files copied manually"
    cd -
fi

# Create .env
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ Created .env"
fi

echo ""
echo "======================================"
echo "  Installation Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. Activate venv: source venv/bin/activate"
echo "  2. Test discovery: python3 test_discovery.py"
echo "  3. Discover cameras: python3 discover_cameras.py"
echo "  4. Start NVR: python3 main.py"
echo ""
