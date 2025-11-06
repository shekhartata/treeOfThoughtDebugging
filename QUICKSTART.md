# Quick Start Guide

## Installation

### Quick Setup
```bash
# Run the setup script
./setup.sh
```

### Manual Setup
```bash
# 1. Create virtual environment
python3 -m venv venv

# 2. Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate     # On Windows

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Set up OpenAI API key (REQUIRED)
cp .env.sample .env
# Edit .env and replace 'sk-your-openai-api-key-here' with your actual API key
# Get your API key from https://platform.openai.com/api-keys
```

**Note:** Always activate the virtual environment before running the tool:
```bash
source venv/bin/activate  # macOS/Linux
```

## Running the Web Interface

```bash
python app.py
```

Then open your browser to: `http://localhost:5000`

## Running the CLI Tool

```bash
python cli_tool.py
```

## Example Workflow

### 1. Initialize Session
- **Web**: Enter problem summary in the text area and click "Initialize"
- **CLI**: Enter problem summary when prompted

Example: `"Writes slow on primary after deploy. Users reporting timeouts."`

### 2. Review Initial Hypotheses
The tool will show 7 initial hypotheses with confidence scores based on priors:
- Indexing (35%)
- Query Shape (25%)
- Schema (20%)
- WT Cache (15%)
- Storage (15%)
- Replication (10%)
- Networking (5%)

### 3. Upload Artifacts
As the tool requests data, upload artifacts:

**Example Artifact 1:**
- Name: `db.currentOp() output`
- Content: Paste the output showing running operations

**Example Artifact 2:**
- Name: `Slow query profile`
- Content: Paste query profile showing COLLSCAN

**Example Artifact 3:**
- Name: `getIndexes() output`
- Content: Paste index definitions

### 4. Monitor Hypothesis Updates
Watch as:
- Evidence is collected
- Confidence scores update
- Low-confidence hypotheses are pruned
- High-confidence hypotheses are accepted

### 5. Get Final Analysis
When sufficient data is gathered:
- Click "Get Final Analysis" (web) or type "final" (CLI)
- Review root cause, evidence, mitigation, and next steps

## Tips

1. **Be Specific**: Provide detailed problem descriptions - LLM uses this to generate hypotheses
2. **Upload Relevant Data**: Focus on artifacts the tool requests
3. **Multiple Artifacts**: You can upload multiple artifacts per step
4. **Backtrack**: Use backtracking to explore alternate hypotheses
5. **Fallback Mode**: If needed, you can use hardcoded hypotheses by passing `use_hardcoded_fallback=True` in the API

## Common Artifacts to Collect

- `db.currentOp()` - Current operations
- `db.serverStatus()` - Server status and metrics
- `db.stats()` - Collection statistics
- `db.collection.getIndexes()` - Index definitions
- `db.system.profile.find()` - Query profiles
- Replication status output
- WiredTiger cache statistics
- Disk I/O metrics

## Troubleshooting

**Port already in use:**
```bash
# Change port in app.py or use:
export FLASK_RUN_PORT=5001
python app.py
```

**LLM not working:**
- Check that OPENAI_API_KEY is set in .env
- Tool requires LLM by default - if you need fallback mode, pass `use_hardcoded_fallback=True`

**Import errors:**
```bash
# Make sure all dependencies are installed
pip install -r requirements.txt
```

