FROM node:24-slim AS admin-build
WORKDIR /build/admin-ui
COPY admin-ui/package.json admin-ui/package-lock.json ./
RUN npm ci
COPY admin-ui/ ./
RUN npm run build

# The storefront is served from its own domain by StorefrontHandler, so it
# calls /api/storefront/* on the same origin and needs no API base URL.
FROM node:24-slim AS storefront-build
WORKDIR /build/storefront
COPY storefront/package.json storefront/package-lock.json ./
RUN npm ci
COPY storefront/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
COPY --from=admin-build --chown=appuser:appuser /build/admin-ui/dist ./admin-ui/dist
COPY --from=storefront-build --chown=appuser:appuser /build/storefront/dist ./storefront/dist

USER appuser

CMD ["python", "railway_server.py"]
