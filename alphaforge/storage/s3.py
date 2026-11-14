from __future__ import annotations

from alphaforge.storage.base import Storage, StorageError, StorageNotFoundError


class S3Storage(Storage):
    """Stockage S3. Identifiants : chaîne par défaut de boto3 (rôle IAM de la tâche ECS, ou profil en local)."""

    def __init__(self, bucket: str, prefix: str = "", region: str | None = None, profile: str | None = None, client=None):
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        if client is None:
            import boto3

            client = boto3.Session(profile_name=profile, region_name=region).client("s3")
        self._s3 = client

    def _key(self, key: str) -> str:
        key = key.lstrip("/")
        if ".." in key.split("/"):
            raise StorageError(f"Clé invalide : {key!r}")
        return f"{self._prefix}/{key}" if self._prefix else key

    def _strip(self, full_key: str) -> str:
        return full_key[len(self._prefix) + 1 :] if self._prefix else full_key

    def put_bytes(self, key: str, data: bytes) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self._s3.put_object(Bucket=self._bucket, Key=self._key(key), Body=data, ServerSideEncryption="AES256")
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Écriture S3 impossible ({key}): {exc}") from exc

    def get_bytes(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return self._s3.get_object(Bucket=self._bucket, Key=self._key(key))["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                raise StorageNotFoundError(key) from exc
            raise StorageError(f"Lecture S3 impossible ({key}): {exc}") from exc
        except BotoCoreError as exc:
            raise StorageError(f"Lecture S3 impossible ({key}): {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            self.get_bytes(key)
        except StorageNotFoundError:
            return False
        return True

    def list(self, prefix: str = "") -> list[str]:
        from botocore.exceptions import BotoCoreError, ClientError

        keys: list[str] = []
        try:
            for page in self._s3.get_paginator("list_objects_v2").paginate(
                Bucket=self._bucket, Prefix=self._key(prefix)
            ):
                keys.extend(self._strip(obj["Key"]) for obj in page.get("Contents", []))
        except (ClientError, BotoCoreError) as exc:
            raise StorageError(f"Listage S3 impossible ({prefix}): {exc}") from exc
        return sorted(keys)
