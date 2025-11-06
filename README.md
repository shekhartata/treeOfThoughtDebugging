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
- 🎯 **Interactive Web UI**: Modern, intuitive interface for debugging sessions
- 🔄 **Backtracking**: Explore alternate hypothesis branches
- 🔁 **Session Management**: Reset sessions to start fresh with new issues
- 🛡️ **Smart Pruning**: Keeps top 2 hypotheses even when evidence is limited

## Installation

### Quick Setup (Recommended)

Run the setup script:
```bash
cd treeOfThoughtProj
./setup.sh
```

This will:
- Create a virtual environment (`venv`)
- Install all dependencies
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

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Set up environment variables (REQUIRED):**
   ```bash
   cp .env.sample .env
   # Edit .env and replace 'sk-your-openai-api-key-here' with your actual API key
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

## Usage

### Starting the Application

```bash
python app.py
```

The web interface will be available at `http://localhost:5000`

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

5. **Get Final Analysis**: When sufficient data is gathered (or even if all hypotheses are pruned), request the final root cause analysis. GPT-5 will provide:
   - Root cause identification
   - Supporting evidence
   - Mitigation strategies
   - Next steps
   - Alternative hypotheses to consider

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

## API Endpoints

The tool provides a REST API for programmatic access:

- `POST /api/initialize` - Initialize a new debugging session
- `POST /api/upload-artifact` - Upload and process an artifact
- `GET /api/current-node` - Get current reasoning state
- `POST /api/backtrack` - Backtrack to a previous node
- `GET /api/final-analysis` - Get root cause analysis (works even if all hypotheses are pruned)
- `GET /api/tree-summary` - Get reasoning tree summary
- `GET /api/history` - Get full reasoning history
- `POST /api/reset` - Reset session and clear all tree content

## Architecture

- **`tot_engine.py`**: Core Tree-of-Thought reasoning engine with hypothesis management and pruning logic
- **`llm_integration.py`**: GPT-5 integration for all LLM operations (hypothesis generation, evaluation, requests, final analysis)
- **`app.py`**: Flask web application and REST API
- **`cli_tool.py`**: Command-line interface alternative
- **`templates/index.html`**: Web interface

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
- **OpenAI API key (REQUIRED)** - The tool uses GPT-5 for all LLM operations

## Notes

- **LLM is REQUIRED** - The tool is fully LLM-driven using GPT-5 for:
  - Hypothesis generation
  - Artifact evaluation
  - Next data requests
  - Final root cause analysis
- **Error Logging**: All LLM failures are logged with detailed error information for debugging
- **Fallback Support**: If LLM fails, the tool falls back to hardcoded hypotheses (pass `use_hardcoded_fallback=True`)
- **Data Privacy**: Customer data is sent to OpenAI API for LLM processing
- **Session Management**: Use "Reset Session" to clear all tree content and start fresh with a new issue
- **Smart Pruning**: Top 2 hypotheses are protected from pruning unless confidence < 5%
- **Comprehensive Analysis**: Final analysis works even when all hypotheses are pruned, providing recommendations based on available artifacts

## Troubleshooting

If you encounter issues with GPT-5:
- Check that your OpenAI API key has access to GPT-5
- Verify the API key is correctly set in `.env` file
- Check error logs for detailed information about LLM failures
- The tool will automatically fall back to hardcoded hypotheses if LLM is unavailable

## License

This tool is designed for internal use by MongoDB Consulting Engineers.

