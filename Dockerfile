FROM python:3.12-slim

# Set environment variables for Railway
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Use Railway's PORT environment variable, fallback to 8051
ENV PORT=${PORT:-8051}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN pip install --no-cache-dir uv

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml ./
COPY README.md ./
COPY uv.lock* ./

# Install dependencies
RUN uv pip install --system --no-cache .

# Copy source code
COPY src/ ./src/

# Run crawl4ai setup
RUN crawl4ai-setup

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Expose the port
EXPOSE ${PORT}

# Command to run the MCP server
CMD ["uv", "run", "src/crawl4ai_mcp.py"] 