# Tree-of-Thought Debugging Tool - React Frontend

This is the React frontend for the MongoDB Tree-of-Thought Debugging Tool.

## Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Development mode:
```bash
npm run dev
```
This will start the Vite dev server on `http://localhost:5173` with proxy to Flask backend at `http://localhost:5000`.

3. Build for production:
```bash
npm run build
```
This will build the React app and output to `../static/` directory, which Flask will serve.

## Project Structure

```
frontend/
├── src/
│   ├── components/      # React components
│   ├── services/        # API service layer
│   ├── styles/          # CSS files
│   ├── App.jsx          # Main app component
│   └── main.jsx         # Entry point
├── public/              # Static assets
├── package.json         # Dependencies
└── vite.config.js       # Vite configuration
```

## Features

- React Flow for interactive tree visualization
- Component-based architecture
- API integration with Flask backend
- Responsive design
- All original features migrated (backtrack, expand, prune, etc.)

