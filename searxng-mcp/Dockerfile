FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SEARXNG_URL=http://searxng:8080 \
    MCP_HTTP_PORT=8077

WORKDIR /srv

# wget is used by the docker-compose healthcheck (/health probe).
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies first (better layer caching)
COPY requirements.txt /srv/requirements.txt
RUN pip install --upgrade pip && pip install -r /srv/requirements.txt

COPY server.py /srv/server.py

# Run as an unprivileged user for safety
RUN useradd -m mcp
USER mcp

EXPOSE 8077

CMD ["python", "server.py"]
