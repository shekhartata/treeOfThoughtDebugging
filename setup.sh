#!/bin/bash
# Setup script for MongoDB Tree-of-Thought Debugging Tool

echo "Setting up MongoDB Tree-of-Thought Debugging Tool..."
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Create virtual environment
echo "1. Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "2. Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "3. Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "4. Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "5. Creating .env file..."
    if [ -f .env.sample ]; then
        cp .env.sample .env
    else
        echo "OPENAI_API_KEY=sk-your-openai-api-key-here" > .env
    fi
    echo "   ⚠️  Please edit .env and add your OPENAI_API_KEY"
else
    echo "5. .env file already exists"
fi

echo ""
echo "✓ Setup complete!"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the web interface:"
echo "  python app.py"
echo ""
echo "To run the CLI tool:"
echo "  python cli_tool.py"
echo ""

