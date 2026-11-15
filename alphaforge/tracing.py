"""MLflow Tracing, optionnel (MLFLOW_TRACING=true) : une trace par analyse, un span par agent et par appel de modèle.

Les traces contiennent les prompts et les réponses (contrairement aux logs JSON) : à réserver au développement, avec un
stockage local (sqlite:///mlflow.db par défaut). Désactivé, `span()` ne fait rien et MLflow n'est même pas importé.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

from alphaforge.config import Settings

_mlflow = None  # module mlflow une fois le tracing activé


def setup_tracing(settings: Settings) -> bool:
    """Active le tracing si la configuration le demande. Retourne True s'il est actif."""
    global _mlflow
    if not settings.mlflow_tracing:
        return False
    import mlflow  # import lourd : seulement si le tracing est demandé

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment)
    _mlflow = mlflow
    return True


class Span:
    """Enveloppe d'un span MLflow ; sans tracing, les appels sont sans effet."""

    def __init__(self, span=None):
        self._span = span

    def outputs(self, outputs: Any) -> None:
        if self._span is not None:
            self._span.set_outputs(outputs)

    def attributes(self, **attributes: Any) -> None:
        if self._span is not None:
            self._span.set_attributes({k: v for k, v in attributes.items() if v is not None})


@contextlib.contextmanager
def span(name: str, span_type: str = "UNKNOWN", inputs: Any = None, **attributes: Any) -> Iterator[Span]:
    """Ouvre un span enfant du span courant (contexte propagé aux threads par LangGraph et `contextvars`)."""
    if _mlflow is None:
        yield Span()
        return
    with _mlflow.start_span(name=name, span_type=span_type) as raw:
        current = Span(raw)
        if inputs is not None:
            raw.set_inputs(inputs)
        current.attributes(**attributes)
        yield current
