"""Interface de stockage : datasets d'évaluation, rapports, artefacts d'expériences, fichiers d'autres équipes."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class StorageError(Exception):
    pass


class StorageNotFoundError(StorageError):
    pass


class Storage(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Clés (triées) commençant par `prefix`."""

    def put_json(self, key: str, obj: Any) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8"))

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))
