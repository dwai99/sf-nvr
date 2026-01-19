#!/bin/bash
# Fix onvif-zeep WSDL files issue

echo "======================================"
echo "  Fixing ONVIF-ZEEP Installation"
echo "======================================"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ERROR: Virtual environment not activated!"
    echo "Please run: source venv/bin/activate"
    exit 1
fi

echo "Uninstalling old onvif-zeep..."
pip uninstall -y onvif-zeep

echo ""
echo "Installing onvif-zeep from git (includes WSDL files)..."
pip install git+https://github.com/FalkTannhaeuser/python-onvif-zeep.git

echo ""
echo "Verifying installation..."
python3 << 'EOF'
from pathlib import Path
import onvif

onvif_path = Path(onvif.__file__).parent
wsdl_path = onvif_path / 'wsdl'

print(f"ONVIF installed at: {onvif_path}")
print(f"WSDL directory exists: {wsdl_path.exists()}")

if wsdl_path.exists():
    import os
    wsdl_files = os.listdir(wsdl_path)
    print(f"WSDL files found: {len(wsdl_files)}")
    if 'devicemgmt.wsdl' in wsdl_files:
        print("✓ devicemgmt.wsdl found!")
    else:
        print("✗ devicemgmt.wsdl NOT found")
else:
    print("✗ WSDL directory NOT found")
EOF

echo ""
echo "======================================"
echo "Fix complete!"
echo "======================================"
echo ""
echo "Now try running: python test_discovery.py"
