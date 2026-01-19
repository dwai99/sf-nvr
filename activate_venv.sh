#!/bin/bash
# Activate virtual environment
# Usage: source activate_venv.sh

if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo ""
    echo "Please create it first:"
    echo "  ./setup.sh"
    echo ""
    echo "Or manually:"
    echo "  python3 -m venv venv"
    return 1 2>/dev/null || exit 1
fi

echo "Activating virtual environment..."
source venv/bin/activate

if [ -n "$VIRTUAL_ENV" ]; then
    echo "✓ Virtual environment activated: $VIRTUAL_ENV"
    echo ""
    echo "You can now run:"
    echo "  python discover_cameras.py  - Discover cameras"
    echo "  python main.py              - Start NVR"
    echo "  python test_discovery.py    - Test discovery"
    echo ""
    echo "To deactivate: deactivate"
else
    echo "❌ Failed to activate virtual environment"
    return 1 2>/dev/null || exit 1
fi
