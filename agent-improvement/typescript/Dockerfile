# Starter Dockerfile — intentionally has ONE real issue for you to fix.
# TODO (candidate): this image currently leaks secrets. `.env` is copied
# into the image and the key can show up in logs / image history.
# Fix it and note it in DESIGN.md.

FROM node:22-slim

WORKDIR /work

# System deps for pg-native builds + healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# BAD (intentional): copies everything including .env into the image layer.
COPY . .

RUN npm ci --no-audit --no-fund
RUN npm run build

ENV NODE_ENV=production

EXPOSE 8000 8001

CMD ["npm", "start"]
