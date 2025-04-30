# https://docs.astral.sh/uv/guides/integration/docker/
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system dependencies for ta-lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    ca-certificates \
    && wget https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz \
    && tar -xvzf ta-lib-0.6.4-src.tar.gz \
    && cd ta-lib-0.6.4/ && ./configure && make && make install \
    && cd .. && rm -rf ta-lib-0.6.4 ta-lib-0.6.4-src.tar.gz \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and uv.lock for dependencies
COPY ./mcp-servers/mcp-trader-main/pyproject.toml ./mcp-servers/mcp-trader-main/uv.lock ./


RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=mcp-servers/mcp-trader-main/uv.lock,target=uv.lock \
    --mount=type=bind,source=mcp-servers/mcp-trader-main/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --no-editable

ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

    
# Use official Python image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

#UV
COPY --from=uv --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"


# Install system dependencies for ta-lib
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    curl \
    ca-certificates \
    && wget https://github.com/ta-lib/ta-lib/releases/download/v0.6.4/ta-lib-0.6.4-src.tar.gz \
    && tar -xvzf ta-lib-0.6.4-src.tar.gz \
    && cd ta-lib-0.6.4/ && ./configure && make && make install \
    && cd .. && rm -rf ta-lib-0.6.4 ta-lib-0.6.4-src.tar.gz \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv using official install script
#RUN curl -LsSf https://astral.sh/uv/install.sh | sh
#ENV PATH="/root/.local/bin:${PATH}"

# Copy requirements and install Python packages using uv
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install ta-lib Python bindings
# RUN pip install --system ta-lib

# Copy application code
COPY mcp-servers /app/mcp-servers/
COPY langgraph_agent.py .
COPY main.py .
COPY servers_config.json .

# Expose port
EXPOSE 8080

# Start FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]