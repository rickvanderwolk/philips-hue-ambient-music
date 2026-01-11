#!/bin/bash
# Setup script for Ambient Music Generator

cd "$(dirname "$0")"

echo "Setting up Ambient Music..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install
echo "Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "Setup complete! Run with:"
echo "  source venv/bin/activate"
echo "  python main.py --mock    # test without Hue"
echo "  python main.py           # with Hue Bridge"
