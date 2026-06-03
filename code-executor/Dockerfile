FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Install Node.js (for JavaScript execution) alongside Python
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip && pip install "fastapi==0.115.6" "uvicorn[standard]==0.34.0"

COPY runner.py /srv/runner.py

# Run as an unprivileged user for safety
RUN useradd -m sandbox
USER sandbox

EXPOSE 9000

CMD ["uvicorn", "runner:app", "--host", "0.0.0.0", "--port", "9000"]
