#!/bin/bash
# SCRS-1913 Test Service Setup Script

set -e

echo "=========================================="
echo "SCRS-1913 Test Service Setup"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp config.template .env
    echo "✓ .env created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your Datadog API key!"
    echo "   DD_API_KEY=your_actual_api_key_here"
    echo ""
else
    echo "✓ .env file already exists"
    echo ""
fi

# Create virtual environment
if [ ! -d venv ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
    echo ""
else
    echo "✓ Virtual environment already exists"
    echo ""
fi

# Activate and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your Datadog API key"
echo "2. Run: source venv/bin/activate"
echo "3. Test Scenario 1 (without DD_APPSEC_ENABLED):"
echo "   ddtrace-run python app.py"
echo ""
echo "See README.md for full testing instructions"





