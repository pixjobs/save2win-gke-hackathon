# Use a current, slim Python
FROM python:3.11-slim

# System deps: CA certs + tini (clean shutdowns)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and writable home/work dirs
RUN useradd -m -u 10001 appuser
WORKDIR /app
RUN chown -R appuser:appuser /app

# Avoid bytecode + ensure unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python deps first (leverage layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Drop root
USER appuser

# Expose HTTP port
EXPOSE 8080

# Use tini as PID 1; start gunicorn
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
