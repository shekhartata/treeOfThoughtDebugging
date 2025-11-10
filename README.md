# MongoDB Tree-of-Thought Debugging Tool

An interactive debugging tool for MongoDB Consulting Engineers that uses Tree-of-Thought (ToT) reasoning to systematically diagnose performance issues.

## Overview

This tool helps Consulting Engineers (CEs) debug MongoDB issues through an iterative, hypothesis-driven approach:

1. **CE inputs** a problem summary
2. **ToT engine** proposes hypotheses and requests specific data
3. **CE uploads** artifacts (logs, metrics, command outputs)
4. **Engine evaluates** evidence and prunes low-confidence hypotheses
5. **Process repeats** until sufficient data is gathered
6. **Final RCA** (Root Cause Analysis) with recommendations

## Features

- 🌳 **Tree-of-Thought Reasoning**: Systematic hypothesis evaluation with branching and pruning
- 📊 **Confidence Scoring**: Multi-factor scoring (priors, LLM evaluation, evidence-based)
- 🔍 **Artifact Processing**: Upload and analyze MongoDB logs, metrics, and command outputs
- 🤖 **LLM-Driven Analysis**: Fully powered by GPT-5 for hypothesis generation, evaluation, and root cause analysis
- 🎯 **Interactive Web UI**: Modern React-based interface with React Flow tree visualization
- 🔄 **Backtracking**: Explore alternate hypothesis branches
- 🎨 **Focused Mode**: Evaluate specific branches after backtracking
- 🔁 **Session Management**: Reset sessions to start fresh with new issues
- 🛡️ **Smart Pruning**: Keeps top 2 hypotheses even when evidence is limited
- 📈 **Node Generation**: Generate new exploration directions from any node
- 🎯 **Final Analysis**: Available at any time, not just when complete

## Prerequisites

1. **Python 3.8+** with pip
2. **Node.js 16+** with npm
3. **OpenAI API Key** (set in `.env` file)

## Installation

### Quick Setup (Recommended)

Run the setup script:
```bash
cd treeOfThoughtProj
./setup.sh
```

This will:
- Create a virtual environment (`venv`)
- Install all Python dependencies
- Create `.env` file from template

### Manual Setup

1. **Create virtual environment:**
   ```bash
   cd treeOfThoughtProj
   python3 -m venv venv
   ```

2. **Activate virtual environment:**
   
   On macOS/Linux:
   ```bash
   source venv/bin/activate
   ```
   
   On Windows:
   ```bash
   venv\Scripts\activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Install React dependencies:**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

5. **Set up environment variables (REQUIRED):**
   ```bash
   # Create .env file in project root
   echo "OPENAI_API_KEY=your_api_key_here" > .env
   # Edit .env and replace with your actual API key
   # Get your API key from https://platform.openai.com/api-keys
   ```

### Activating Virtual Environment

After initial setup, activate the virtual environment before running the tool:

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You'll see `(venv)` in your terminal prompt when it's active.

## Running the Application

### Option 1: Development Mode (Recommended for Development)

**Terminal 1 - Start Flask Backend:**
```bash
# Activate virtual environment if not already active
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start Flask server
python app.py
```
Flask will run on `http://localhost:5000`

**Terminal 2 - Start React Frontend:**
```bash
cd frontend
npm run dev
```
React dev server will run on `http://localhost:5173`

**Access the app:** Open `http://localhost:5173` in your browser

The React dev server automatically proxies API requests to Flask at `http://localhost:5000`.

### Option 2: Production Mode (Recommended for Production)

**Step 1 - Build React App:**
```bash
cd frontend
npm run build
cd ..
```

**Step 2 - Start Flask Server:**
```bash
# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start Flask (will serve React build)
python app.py
```

**Access the app:** Open `http://localhost:5000` in your browser

## Usage

### Workflow

1. **Initialize Session**: Enter a problem summary (e.g., "Writes slow on primary after deploy")

2. **Review Hypotheses**: The tool uses GPT-5 to generate initial hypotheses based on your problem description. Hypotheses are dynamically created and tailored to your specific issue.

3. **Upload Artifacts**: As the tool requests specific data, upload:
   - `db.currentOp()` output
   - Query profiles
   - `db.serverStatus()` output
   - `db.stats()` output
   - Index information
   - Any other relevant diagnostics

4. **Monitor Progress**: Watch as hypotheses are:
   - **Evaluated** by GPT-5 based on artifact evidence
   - **Pruned** if confidence drops below threshold (0.3), but top 2 hypotheses are protected unless confidence < 5%
   - **Accepted** if confidence exceeds threshold (0.7)

5. **Interactive Features**:
   - **Backtrack**: Click "Backtrack" on any node to focus on that branch for future evaluations
   - **Generate**: Click "Generate" on any node to create new exploration directions
   - **Prune/Restore**: Manually prune or restore hypotheses
   - **Focus Branch**: Select specific branches to evaluate
   - **Final Analysis**: Available at any time - click "Get Final Analysis" whenever you want

6. **Get Final Analysis**: Request the final root cause analysis. GPT-5 will provide:
   - Root cause identification
   - Supporting evidence
   - Mitigation strategies
   - Next steps
   - Alternative hypotheses to consider

### Key Features

- **Hypothesis Numbering**: Hypotheses are numbered (Hypothesis 1, Hypothesis 2, etc.) to match LLM references
- **Branch Selection**: When multiple active branches exist, select which ones to evaluate
- **Focused Mode**: After backtracking, only the focused branch is evaluated (until you unfocus)
- **Tree Visualization**: View the complete reasoning tree with React Flow
- **End Session**: Use "End Debugging Session" button to reset and start fresh

## Scoring System

The tool uses a weighted confidence scoring formula:

```
score = w_prior * prior + w_llm * llm_score
```

**Default Weights:**
- Prior: 30%
- LLM evaluation: 70%

**Confidence Levels:**
- **HIGH** (0.7-1.0): Strong evidence, likely root cause
- **MEDIUM** (0.4-0.69): Moderate evidence, needs more data
- **LOW** (0.0-0.39): Weak evidence, will be pruned (except top 2 hypotheses)

**Pruning Protection:**
- The top 2 highest-scored hypotheses are always kept unless their confidence drops below 5%
- This prevents all hypotheses from being pruned when limited data is available

## LLM-Powered Analysis

The tool uses GPT-5 to:

- **Generate Hypotheses**: Creates context-aware hypotheses based on problem description
- **Evaluate Evidence**: Analyzes artifacts to update hypothesis confidence scores
- **Generate Requests**: Suggests specific MongoDB commands/outputs to collect next
- **Root Cause Analysis**: Provides comprehensive final analysis with mitigation strategies

All analysis is performed by GPT-5, ensuring the tool can handle any MongoDB issue, not just predefined scenarios.

## Architecture

### Backend
- **`tot_engine.py`**: Core Tree-of-Thought reasoning engine with hypothesis management and pruning logic
- **`llm_integration.py`**: GPT-5 integration for all LLM operations (hypothesis generation, evaluation, requests, final analysis)
- **`app.py`**: Flask web application and REST API
- **`cli_tool.py`**: Command-line interface alternative

### Frontend
- **`frontend/src/App.jsx`**: Main React application component
- **`frontend/src/components/`**: React components (TreeView, HypothesesList, ArtifactUpload, etc.)
- **`frontend/src/services/api.js`**: API client for Flask backend
- **`frontend/src/styles/`**: CSS files for components
- **React Flow**: Used for interactive tree visualization

### Templates
- **`templates/index.html`**: Legacy HTML template (fallback if React build doesn't exist)

## API Endpoints

The tool provides a REST API for programmatic access:

- `POST /api/initialize` - Initialize a new debugging session
- `POST /api/upload-artifact` - Upload and process an artifact
- `GET /api/current-node` - Get current reasoning state
- `POST /api/backtrack` - Backtrack to a previous node
- `POST /api/generate-node` - Generate new exploration directions from a node
- `POST /api/focus-branch` - Focus on a specific branch for evaluation
- `POST /api/unfocus` - Clear focus and evaluate all active branches
- `POST /api/prune-branch` - Manually prune a branch
- `POST /api/unprune-branch` - Restore a pruned branch
- `GET /api/final-analysis` - Get root cause analysis (available at any time)
- `GET /api/tree-summary` - Get reasoning tree summary
- `GET /api/history` - Get full reasoning history
- `POST /api/reset` - Reset session and clear all tree content

## Example Session

1. **Input**: "Writes slow on primary after deploy"

2. **Tool Output** (GPT-5 generated): 
   - Hypotheses: Dynamically generated based on problem (e.g., indexing issues, query shape problems, schema design, cache pressure)
   - Next requests: `db.currentOp()`, slow query profiles, server status

3. **Upload**: `db.currentOp()` output showing COLLSCAN operations

4. **Tool Output** (GPT-5 evaluated):
   - Indexing hypothesis confidence increases based on LLM analysis
   - Evidence: GPT-5 identifies specific patterns in the artifact
   - Next requests: GPT-5 suggests `getIndexes()` output or query profiles

5. **Upload**: Indexes JSON showing missing compound index

6. **Tool Output** (GPT-5 final analysis):
   - Root cause: Missing compound index identified by GPT-5
   - Evidence: Specific findings from artifacts
   - Mitigation: Detailed steps to create appropriate index
   - Next steps: Additional recommendations for optimization

## Requirements

- Python 3.8+
- Flask 3.0+
- Node.js 16+
- **OpenAI API key (REQUIRED)** - The tool uses GPT-5 for all LLM operations

## Important Notes

- **LLM is REQUIRED** - The tool is fully LLM-driven using GPT-5 for:
  - Hypothesis generation
  - Artifact evaluation
  - Next data requests
  - Final root cause analysis
- **Error Logging**: All LLM failures are logged with detailed error information for debugging
- **Fallback Support**: If LLM fails, the tool falls back to hardcoded hypotheses (pass `use_hardcoded_fallback=True`)
- **Data Privacy**: Customer data is sent to OpenAI API for LLM processing
- **Session Management**: Use "End Debugging Session" to clear all tree content and start fresh with a new issue
- **Smart Pruning**: Top 2 hypotheses are protected from pruning unless confidence < 5%
- **Final Analysis**: Available at any time, not just when session is complete
- **Ephemeral Sessions**: Current implementation stores sessions in memory only - data is lost on server restart

## Troubleshooting

### Flask Server Issues

**Port already in use:**
- Change Flask port in `app.py`: `app.run(debug=True, port=5001)`
- Or kill the process using port 5000

**Session resets automatically:**
- Flask's debug mode auto-reloader watches for file changes
- Any file change (including `__pycache__` updates) triggers a restart
- This is expected behavior in development mode
- For production, use `app.run(debug=False, use_reloader=False)`

**Engine not initialized error:**
- Make sure you've initialized a session first
- Check that Flask server is running
- Verify API key is set in `.env` file

### React Frontend Issues

**Port already in use:**
- Vite will automatically use the next available port (5174, 5175, etc.)
- Check terminal output for the actual port number
- Or change port in `frontend/vite.config.js`

**API connection errors:**
- Make sure Flask is running before starting React
- Check that Flask is on port 5000 (or update proxy in `vite.config.js`)
- Check browser console for detailed error messages

**Build errors:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

### LLM/API Issues

**GPT-5 errors:**
- Check that your OpenAI API key has access to GPT-5
- Verify the API key is correctly set in `.env` file
- Check error logs for detailed information about LLM failures
- The tool will automatically fall back to hardcoded hypotheses if LLM is unavailable

**Rate limiting:**
- OpenAI API has rate limits
- Reduce frequency of artifact uploads
- Consider caching LLM responses (future enhancement)

### General Issues

**Python packages not found:**
```bash
pip install -r requirements.txt
```

**React dependencies not found:**
```bash
cd frontend
npm install
```

**Virtual environment not activating:**
- Make sure you're in the project root directory
- Check that `venv/` directory exists
- Try recreating: `python3 -m venv venv`

## Project Structure

```
treeOfThoughtProj/
├── app.py                 # Flask web application
├── tot_engine.py          # Core ToT reasoning engine
├── llm_integration.py     # GPT-5 integration
├── cli_tool.py            # Command-line interface
├── test_demo.py           # Demo/test script
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── setup.sh               # Setup script
├── README.md              # This file
├── EVALUATION.md          # Project evaluation and use cases
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/    # React components
│   │   ├── services/      # API client
│   │   ├── styles/        # CSS files
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── templates/             # Legacy HTML template
├── static/                # Production build output (after npm run build)
└── venv/                  # Virtual environment (created by setup)
```

## License

This tool is designed for internal use by MongoDB Consulting Engineers.

## Additional Documentation

- **EVALUATION.md**: Comprehensive project evaluation, use cases, and automation analysis
