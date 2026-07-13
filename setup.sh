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
        cat > .env << 'EOF'
# LLM Provider Configuration
# Available providers: openai, groq
LLM_PROVIDER=openai

# OpenAI API Key (for GPT-5)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Groq API Key (for DeepSeek-R1-Distill-Llama-70B - faster inference)
# Get your key at: https://console.groq.com/keys
GROQ_API_KEY=gsk-your-groq-api-key-here
EOF
    fi
    echo "   ⚠️  Please edit .env and add your API keys"
    echo "   ⚠️  Set LLM_PROVIDER=groq for faster inference"
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

