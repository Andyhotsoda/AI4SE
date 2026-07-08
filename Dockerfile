FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY pyproject.toml .
COPY harness/ ./harness/
COPY cli/ ./cli/
COPY tests/ ./tests/
COPY demos/ ./demos/
COPY Makefile .

# Install the package
RUN pip install -e .

# Default command: show help
CMD ["python", "-m", "harness"]