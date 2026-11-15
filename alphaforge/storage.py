"""Stockage des datasets, rapports et baselines : dossier local ou bucket S3."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from alphaforge.config import Settings

DATASETS, REPORTS, BASELINES = "datasets", "reports", "baselines"  # préfixes de clés


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
    def list(self, prefix: str = "") -> list[str]: ...

    def put_json(self, key: str, obj: Any) -> None:
        self.put_bytes(key, json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8"))

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_bytes(key).decode("utf-8"))


class LocalStorage(Storage):
    def __init__(self, root: str | Path):
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root not in path.parents:  # interdit "../" hors du dossier racine
            raise StorageError(f"Clé invalide : {key!r}")
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

    def list(self, prefix: str = "") -> list[str]:
        keys = (p.relative_to(self._root).as_posix() for p in self._root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix))


class S3Storage(Storage):
    def __init__(self, bucket: str, prefix: str, region: str, profile: str | None):
        self._bucket, self._prefix = bucket, prefix.strip("/")
        self._s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")

    def _key(self, key: str) -> str:
        if ".." in key.split("/"):
            raise StorageError(f"Clé invalide : {key!r}")
        return f"{self._prefix}/{key.lstrip('/')}" if self._prefix else key.lstrip("/")

    def put_bytes(self, key: str, data: bytes) -> None:
        try:
            self._s3.put_object(Bucket=self._bucket, Key=self._key(key), Body=data, ServerSideEncryption="AES256")
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Écriture S3 impossible ({key}): {exc}") from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            return self._s3.get_object(Bucket=self._bucket, Key=self._key(key))["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise StorageNotFoundError(key) from exc
            raise StorageError(f"Lecture S3 impossible ({key}): {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Lecture S3 impossible ({key}): {exc}") from exc

    def list(self, prefix: str = "") -> list[str]:
        strip = len(self._prefix) + 1 if self._prefix else 0
        try:
            pages = self._s3.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=self._key(prefix))
            return sorted(obj["Key"][strip:] for page in pages for obj in page.get("Contents", []))
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Listage S3 impossible ({prefix}): {exc}") from exc


def get_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_dir)
    if settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise StorageError("STORAGE_BACKEND=s3 exige S3_BUCKET")
        return S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region, settings.aws_profile)
    raise StorageError(f"STORAGE_BACKEND inconnu : {settings.storage_backend!r} (local | s3)")
