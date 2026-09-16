# Starter Dockerfile — intentionally has ONE real issue for you to fix.
# TODO (candidate): this image currently leaks secrets. `.env` is copied
# into the image and the key can show up in logs / image history.
# Fix it and note it in DESIGN.md.

FROM python:3.12-slim

WORKDIR /work

# System deps for psycopg + healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# BAD (intentional): copies everything including .env into the image layer.
COPY . .

RUN uv sync --frozen --no-dev

ENV PATH="/work/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000 8001

CMD ["python", "-m", "src.main"]
