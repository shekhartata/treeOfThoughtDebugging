# Stage 1: Build React frontend (Vite outDir is ../static, so run from frontend/ → static at /app/static)
FROM node:20-alpine AS frontend
WORKDIR /app
COPY frontend/ ./frontend/
WORKDIR /app/frontend
# Avoid EPIPE / OOM during vite/esbuild when building for another platform (e.g. --platform linux/amd64)
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN npm ci && npm run build

# Stage 2: Python app (serves API + static)
FROM python:3.11-slim
WORKDIR /app

COPY app.py auth.py session_manager.py tot_engine.py llm_integration.py bayesian_pruner.py ./
COPY llm_adapters/ ./llm_adapters/
COPY templates/ ./templates/
COPY requirements.txt ./
COPY --from=frontend /app/static ./static

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000
ENV FLASK_APP=app.py

# Production: gunicorn; bind to 0.0.0.0 for K8s
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
