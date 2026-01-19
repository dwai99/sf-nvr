#!/bin/bash
# SF-NVR Setup Script
# This script sets up the virtual environment and installs dependencies

set -e  # Exit on error

echo "================================================"
echo "  SF-NVR - Network Video Recorder Setup"
echo "================================================"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Found Python $PYTHON_VERSION"

# Check for FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "Warning: FFmpeg is not installed"
    echo "FFmpeg is required for video processing"
    echo ""
    echo "Install FFmpeg:"
    echo "  macOS:         brew install ffmpeg"
    echo "  Ubuntu/Debian: sudo apt-get install ffmpeg"
    echo ""
    read -p "Continue without FFmpeg? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "Found FFmpeg: $(ffmpeg -version | head -n1 | cut -d' ' -f3)"
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists"
    read -p "Recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        python3 -m venv venv
    fi
else
    python3 -m venv venv
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing Python dependencies..."
echo "(This may take a few minutes...)"
pip install -r requirements.txt

# Verify onvif-zeep WSDL files
echo ""
echo "Verifying ONVIF installation..."
python3 << 'VERIFY_EOF'
from pathlib import Path
try:
    import onvif
    onvif_path = Path(onvif.__file__).parent
    wsdl_path = onvif_path / 'wsdl'
    if wsdl_path.exists():
        print("✓ ONVIF WSDL files found")
    else:
        print("⚠ ONVIF WSDL files missing - this is OK, will be fixed on first run")
except ImportError:
    print("⚠ ONVIF not yet installed")
VERIFY_EOF

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "Created .env - you can edit this file to set camera credentials"
fi

# Success message
echo ""
echo "================================================"
echo "  Setup Complete!"
echo "================================================"
echo ""
echo "To start the NVR:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run the application:"
echo "     python main.py"
echo ""
echo "  3. Open your browser to:"
echo "     http://localhost:8080"
echo ""
echo "To deactivate the virtual environment:"
echo "  deactivate"
echo ""
echo "Configuration:"
echo "  - Edit config/config.yaml for settings"
echo "  - Edit .env for camera credentials"
echo ""