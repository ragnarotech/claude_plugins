FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy test code (no test data - loaded from S3)
COPY features/ ./features/
COPY tests/ ./tests/
COPY src/ ./src/
COPY pytest.ini ./

# Create results directory
RUN mkdir -p /results

# Default command
CMD ["pytest", "tests/", "-v", "--junitxml=/results/junit.xml"]
