FROM python:3.12-slim

# Set environment variables for Railway
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies including Playwright browser dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
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
COPY start_rest_api.py ./

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Run crawl4ai setup and install playwright browsers as the app user
RUN crawl4ai-setup
RUN playwright install chromium

# Use our startup script that properly handles Railway's PORT environment variable
CMD ["python", "start_rest_api.py"] 