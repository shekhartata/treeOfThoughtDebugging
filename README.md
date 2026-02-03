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

### Core ToT & Analysis
- 🌳 **Tree-of-Thought Reasoning**: Systematic hypothesis evaluation with branching and pruning
- 📊 **Confidence Scoring**: Multi-factor scoring (priors, LLM evaluation, evidence-based)
- 🔍 **Artifact Processing**: Upload and analyze MongoDB logs, metrics, and command outputs
- 🤖 **LLM-Driven Analysis**: Hypothesis generation, evaluation, and root cause analysis (OpenAI, Groq, Ollama)
- 🎯 **Interactive Web UI**: Modern React-based interface with React Flow tree visualization
- 🔄 **Backtracking**: Explore alternate hypothesis branches
- 🎨 **Focused Mode**: Evaluate specific branches after backtracking
- 🔁 **Session Management**: Reset sessions to start fresh with new issues
- 🛡️ **Smart Pruning**: Keeps top 2 hypotheses even when evidence is limited
- 📈 **Node Generation**: Generate new exploration directions from any node
- 🎯 **Final Analysis**: Available at any time, not just when complete

### Authentication & Multi-User
- 🔐 **Sign in / Sign up**: JWT-based auth; register and log in with email/password
- 👤 **Owner vs Collaborator**: Boards belong to the creating user; header shows "Owner" or "Collaborator"
- 📤 **Share boards**: Owner can share via link; search users by name/email and add them to the board
- 🔗 **Restricted sharing**: Share links work only for users the owner has added; sign-in required to open a shared link
- 🚪 **Sign out**: Clear session and board; next user sees Login and never the previous user’s board

## Prerequisites

1. **Python 3.8+** with pip
2. **Node.js 16+** with npm
3. **OpenAI API Key** (or Groq) and **JWT_SECRET** in `.env` (see [Environment variables](#environment-variables))
4. **MongoDB** (optional; used for session and user persistence; defaults to local MongoDB if `MONGODB_URI` is not set)

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
   cp .env.sample .env
   # Edit .env and set at least:
   # - OPENAI_API_KEY (or GROQ_API_KEY if using Groq)
   # - JWT_SECRET (e.g. openssl rand -hex 32)
   # - MONGODB_URI (if not using default local MongoDB)
   ```
   See [Environment variables](#environment-variables) below for the full list.

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

### Important: Both servers for development

When using **Option 1** (Vite dev server on port 5173), the frontend proxies `/api` to Flask on port 5000. **Start Flask first** (Terminal 1), then start the frontend (Terminal 2). If Flask is not running, you will see `ECONNREFUSED` in the terminal and the app may show a loading or login screen that never completes.

## Environment variables

Create a `.env` file in the project root (e.g. `cp .env.sample .env`) and set:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes (or Groq) | OpenAI API key for LLM; see [LLM Provider Configuration](#llm-provider-configuration) |
| `JWT_SECRET` | Yes | Secret for JWT signing (min 32 chars); e.g. `openssl rand -hex 32` |
| `MONGODB_URI` | No | MongoDB connection string; default uses local MongoDB |
| `MONGODB_DATABASE_NAME` | No | Database name; default `tot_debugging` |
| `LLM_PROVIDER` | No | `openai`, `groq`, or `ollama` |
| `GROQ_API_KEY` | If Groq | Groq API key when using Groq provider |

## Usage

### Authentication and sharing

1. **Sign in**: Open the app; you’ll see the Login screen. Sign in or create an account (email + password).
2. **Owner view**: After signing in, start a new board (problem summary). You are the **Owner**; the header shows “Owner” and a **Share** button.
3. **Share a board**: Click **Share**, search for users by name or email, add them, then copy the share link. Only those users (and you) can open the link after signing in.
4. **Open a shared link**: Open the link in a browser; sign in if prompted. If you’re one of the users the owner added, you’ll see the board as **Collaborator** (no Share button).
5. **Sign out**: Click **Sign out** in the header. Session and board are cleared; the next user will see the Login screen and never the previous user’s board.

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
- **`app.py`**: Flask web application and REST API (sessions, auth, share, ToT endpoints)
- **`auth.py`**: JWT auth, user registration/login, user search, `AuthManager`
- **`tot_engine.py`**: Core Tree-of-Thought reasoning engine with hypothesis management and pruning logic
- **`llm_integration.py`**: LLM integration for hypothesis generation, evaluation, and analysis (OpenAI, Groq, Ollama)
- **`session_manager.py`**: MongoDB persistence for sessions and nodes; `owner_id` and `shared_with` for access control
- **`cli_tool.py`**: Command-line interface alternative

### Frontend
- **`frontend/src/App.jsx`**: Main React app (auth gate, loading, Login, init form, board view, Share, Sign out)
- **`frontend/src/contexts/AuthContext.jsx`**: Auth state, login/register/logout, JWT in localStorage
- **`frontend/src/components/`**: Login, InitializeForm, CurrentState, TreeView, ShareModal, ErrorBoundary, etc.
- **`frontend/src/services/api.js`**: API client (auth, sessions, join, share-with, board token)
- **`frontend/src/styles/`**: CSS for components
- **React Flow**: Interactive tree visualization

### Templates
- **`templates/index.html`**: Legacy HTML template (fallback if React build doesn't exist)
- **`static/`**: React production build (after `npm run build`); Flask serves `static/index.html` when present

## API Endpoints

The tool provides a REST API for programmatic access.

### Auth
- `POST /api/auth/register` - Register (email, password, optional name); returns user and JWT
- `POST /api/auth/login` - Login (email, password); returns user and JWT
- `GET /api/auth/me` - Current user (requires `Authorization: Bearer <token>`)

### Sharing and access
- `GET /api/join?token=<share_token>` - Join a board by share link (requires login; user must be owner or in `shared_with`)
- `POST /api/sessions/<session_id>/share-token` - Get or create share token (owner only)
- `GET /api/users/search?q=<query>` - Search users by name/email (auth required)
- `POST /api/sessions/<session_id>/share-with` - Add user to board’s `shared_with` (owner only)
- `GET /api/sessions/<session_id>/shared-with` - List users the board is shared with
- `GET /api/check-session` - Check if session exists and current user has access; optional `?session_id=`

### ToT and session
- `POST /api/initialize` - Initialize a new debugging session
- `POST /api/upload-artifact` - Upload and process an artifact
- `GET /api/current-node` - Get current reasoning state (includes `is_owner`)
- `POST /api/backtrack` - Backtrack to a previous node
- `POST /api/generate-node` - Generate new exploration directions from a node
- `POST /api/focus-branch` - Focus on a specific branch for evaluation
- `POST /api/unfocus` - Clear focus and evaluate all active branches
- `POST /api/prune-branch` - Manually prune a branch
- `POST /api/unprune-branch` - Restore a pruned branch
- `POST /api/add-branch` - Add a manual hypothesis (branch)
- `GET /api/final-analysis` - Get root cause analysis (available at any time)
- `GET /api/tree-summary` - Get reasoning tree summary
- `GET /api/history` - Get full reasoning history
- `POST /api/reset` - Reset session and clear all tree content
- `GET /api/sessions/<session_id>/load` - Load session (owner or shared_with)
- `POST /api/sessions/<session_id>/save` - Save session

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
- **LLM API key (REQUIRED)** - One of the following:
  - OpenAI API key (for GPT-5) - default
  - Groq API key (for DeepSeek-R1-Distill-Llama-70B) - faster inference

## LLM Provider Configuration

The tool supports multiple LLM providers via an adapter pattern. You can switch providers without code changes.

### Available Providers

| Provider | Model | Speed | Notes |
|----------|-------|-------|-------|
| `openai` | GPT-5 | ~50 tokens/sec | Default, high quality |
| `groq` | DeepSeek-R1-Distill-Llama-70B | ~300+ tokens/sec | Fast inference, good for ToT |

### Switching Providers

**Option 1: Environment Variable**
```bash
# Use OpenAI (default)
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-your-key-here

# Use Groq (faster)
export LLM_PROVIDER=groq
export GROQ_API_KEY=gsk-your-key-here
```

**Option 2: .env File**
```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk-your-key-here
OPENAI_API_KEY=sk-your-key-here
```

### Getting API Keys

- **OpenAI**: https://platform.openai.com/api-keys
- **Groq**: https://console.groq.com/keys (free tier available)

## Important Notes

- **LLM is REQUIRED** - The tool is fully LLM-driven for:
  - Hypothesis generation
  - Artifact evaluation
  - Next data requests
  - Final root cause analysis
- **Auth** - Sign in or register to use the app. JWT is stored in the browser; set `JWT_SECRET` in `.env`.
- **Sharing** - Only the board owner can share. Share links require sign-in; only users the owner added (or the owner) can open the link.
- **Session persistence** - Sessions and nodes are stored in MongoDB; boards have `owner_id` and `shared_with` for access control.
- **Sign out** - Clears session and board so the next user always sees Login.
- **Adapter Pattern**: LLM providers are swappable via `llm_adapters/` and UI (InitializeForm).
- **Fallback Support**: If LLM fails, the tool can use hardcoded hypotheses (`use_hardcoded_fallback=True`).
- **Data Privacy**: Customer data may be sent to the configured LLM API for processing.
- **Smart Pruning**: Top 2 hypotheses are protected from pruning unless confidence < 5%.
- **Final Analysis**: Available at any time, not just when session is complete.

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

**API connection errors / ECONNREFUSED:**
- Start **Flask first** (Terminal 1: `python app.py`), then start the frontend (Terminal 2: `cd frontend && npm run dev`)
- Vite proxies `/api` to `http://localhost:5000`; if Flask isn’t running, requests fail and the app can stick on loading or login
- For production (Flask only on port 5000), run `cd frontend && npm run build` so Flask serves the latest React build from `static/`

**Build errors:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run build
```

### LLM/API Issues

**LLM errors:**
- Check that your API key is correctly set in `.env` file
- Verify `LLM_PROVIDER` matches your API key (openai or groq)
- Check error logs for detailed information about LLM failures
- The tool will automatically fall back to hardcoded hypotheses if LLM is unavailable

**Switching providers:**
```bash
# If OpenAI is slow or unavailable, try Groq:
export LLM_PROVIDER=groq
export GROQ_API_KEY=gsk-your-key-here
```

**Rate limiting:**
- Both OpenAI and Groq have rate limits
- Groq has generous free tier for testing
- Reduce frequency of artifact uploads if hitting limits

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
├── app.py                 # Flask web application and REST API
├── auth.py                # JWT auth, AuthManager, user CRUD, search
├── session_manager.py    # MongoDB sessions/nodes; owner_id, shared_with
├── tot_engine.py          # Core ToT reasoning engine
├── llm_integration.py     # LLM integration (thin wrapper over adapters)
├── llm_adapters/          # LLM adapter pattern implementation
│   ├── __init__.py        # Package exports
│   ├── base_adapter.py    # Abstract base class for adapters
│   ├── config.py          # Provider configuration and factory
│   ├── openai_adapter.py  # OpenAI adapter
│   ├── groq_adapter.py    # Groq adapter (fast inference)
│   └── ollama_adapter.py  # Ollama (local) adapter
├── cli_tool.py            # Command-line interface
├── test_demo.py           # Demo/test script
├── requirements.txt      # Python dependencies
├── .env                   # Environment variables (create from .env.sample)
├── .env.sample            # Example env vars
├── setup.sh               # Setup script
├── README.md              # This file
├── EVALUATION.md          # Project evaluation and use cases
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/    # Login, InitializeForm, CurrentState, ShareModal, ErrorBoundary, etc.
│   │   ├── contexts/      # AuthContext
│   │   ├── services/      # api.js (auth, sessions, join, share)
│   │   ├── styles/        # CSS files
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js     # Vite config; proxy /api -> localhost:5000
├── templates/             # Legacy HTML template (fallback)
├── static/                # React production build (after npm run build)
└── venv/                  # Virtual environment (created by setup)
```

## License

This tool is designed for internal use by MongoDB Consulting Engineers.

## Additional Documentation

- **EVALUATION.md**: Comprehensive project evaluation, use cases, and automation analysis
