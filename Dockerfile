# Image unique : interface React compilée + API Flask (gunicorn). Déployée sur ECS Fargate (deploy/), ARM64.
# Les identifiants AWS viennent du rôle IAM de la tâche ECS, jamais de l'image. Le jeu de départ est lu sur S3.

# 1) Interface
FROM node:22-slim AS front
WORKDIR /front
COPY alphaforge-ai/package.json alphaforge-ai/package-lock.json ./
RUN npm ci
COPY alphaforge-ai/ ./
RUN npm run build

# 2) API
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FRONTEND_DIST=/app/frontend
WORKDIR /app
COPY server/requirements-api.txt ./
RUN pip install -r requirements-api.txt
COPY alphaforge ./alphaforge
COPY server ./server
COPY data/datasets ./data/datasets
COPY --from=front /front/dist ./frontend
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 5000
# 1 processus (limites de débit en mémoire) et des threads pour les flux SSE concurrents ; une analyse dure ~100 s.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "1", "--threads", "16", "--timeout", "300", "server.src.main:app"]
