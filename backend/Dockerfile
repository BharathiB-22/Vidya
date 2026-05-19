# ── Stage 1: build ────────────────────────────────────────────────────────────
# Pinned to a specific digest to guarantee a reproducible base layer.
# To update: docker manifest inspect python:3.12-slim | grep digest
FROM python:3.12-slim@sha256:bf73779de6dbd030f3d189eeeb246286965832761ace318c1518300f76c0840d AS builder

WORKDIR /build

# Install compiler tools needed by some Python extension modules (e.g. bcrypt).
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtualenv so only its /venv directory needs to be
# copied to the runtime stage — no stray packages in site-packages.
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy the package manifest and full source so setuptools can resolve the
# package and install all production dependencies in a single layer.
COPY pyproject.toml ./
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir .


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim@sha256:bf73779de6dbd030f3d189eeeb246286965832761ace318c1518300f76c0840d AS runtime

# Non-root system user — no home directory, no interactive shell.
RUN useradd -r -u 1001 -s /sbin/nologin vidya

WORKDIR /app

# Copy only the virtualenv from the builder stage; no build tools in runtime.
COPY --from=builder --chown=vidya:vidya /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy only the artifacts the app needs at runtime.
COPY --chown=vidya:vidya app/      ./app/
COPY --chown=vidya:vidya alembic/  ./alembic/
COPY --chown=vidya:vidya alembic.ini ./

USER vidya

EXPOSE 8000

# Liveness check via the /healthz endpoint (returns 200 as long as the
# process is alive, regardless of external service health).
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
        "import urllib.request, sys; \
         r = urllib.request.urlopen('http://localhost:8000/healthz', timeout=4); \
         sys.exit(0 if r.status == 200 else 1)"

# One Uvicorn worker per container.  Horizontal scaling is handled by
# Kubernetes pod replicas, not by in-process forking.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
