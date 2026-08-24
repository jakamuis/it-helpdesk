FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG BUILD_COMMIT=unknown
LABEL org.opencontainers.image.title="IT Helpdesk Asset Sync" \
      org.opencontainers.image.version="1.1.0" \
      org.opencontainers.image.revision="$BUILD_COMMIT"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip check

# Copy only runtime application code. Secrets, audit data, tests, and helper
# scripts must never become image layers.
RUN groupadd --system --gid 10001 assetsync \
    && useradd --system --uid 10001 --gid assetsync --home-dir /app --shell /usr/sbin/nologin assetsync
COPY --chown=assetsync:assetsync app ./app
RUN mkdir -p /app/data \
    && chown assetsync:assetsync /app/data \
    && chmod 0700 /app/data

# Expose port
EXPOSE 8000

USER assetsync

# Restrictive umask keeps SQLite files and any sidecars private in the volume.
CMD ["sh", "-c", "umask 077 && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
