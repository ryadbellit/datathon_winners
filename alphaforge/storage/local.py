from __future__ import annotations

from pathlib import Path

from alphaforge.storage.base import Storage, StorageError, StorageNotFoundError


class LocalStorage(Storage):
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root != path and self._root not in path.parents:  # interdit "../" hors du dossier racine
            raise StorageError(f"Clé invalide (sort du dossier de stockage) : {key!r}")
        return path

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        if not self._root.exists():
            return []
        keys = (p.relative_to(self._root).as_posix() for p in self._root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix))
