FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn jinja2 aiofiles openai keyrings.alt

# Copy source code
COPY pyproject.toml .
COPY harness/ ./harness/
COPY cli/ ./cli/
COPY tests/ ./tests/
COPY demos/ ./demos/
COPY webui.py .
COPY Makefile .

# Install the package
RUN pip install -e .

# Working directory for agent projects (mount your code here)
VOLUME ["/workspace"]

# Expose WebUI port
EXPOSE 8000

# Default: start WebUI
# Set DEEPSEEK_API_KEY via environment variable when running:
#   docker run -e DEEPSEEK_API_KEY=sk-xxx -p 8000:8000 -v $(pwd):/workspace coding-agent-harness
ENV HARNESS_WORK_DIR=/workspace
CMD ["python", "webui.py", "--dir", "/workspace", "--host", "0.0.0.0", "--port", "8000"]