# Image prête pour ECS Fargate (aucun déploiement n'est lancé par ce dépôt).
# Les identifiants AWS viennent du rôle IAM de la tâche ECS, jamais de l'image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY alphaforge ./alphaforge
RUN pip install .

COPY data/datasets ./data/datasets
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Aucun serveur HTTP dans ce MVP (le frontend/API appartient à d'autres membres de l'équipe).
# La définition de tâche ECS surcharge la commande, ex. : ["python", "-m", "alphaforge", "evaluate", "--dataset", "golden_v1"]
ENTRYPOINT ["python", "-m", "alphaforge"]
CMD ["--help"]
