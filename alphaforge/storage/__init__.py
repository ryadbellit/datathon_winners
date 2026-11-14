from alphaforge.config import Settings
from alphaforge.storage.base import Storage, StorageError, StorageNotFoundError
from alphaforge.storage.local import LocalStorage

# Préfixes de clés conseillés
DATASETS, REPORTS, ARTIFACTS, EXTERNAL, BASELINES = "datasets", "reports", "artifacts", "external", "baselines"


def get_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "local":
        return LocalStorage(settings.local_storage_dir)
    if settings.storage_backend == "s3":
        from alphaforge.storage.s3 import S3Storage  # boto3 chargé seulement si S3 est choisi

        if not settings.s3_bucket:
            raise StorageError("STORAGE_BACKEND=s3 exige S3_BUCKET")
        return S3Storage(settings.s3_bucket, settings.s3_prefix, settings.aws_region, settings.aws_profile)
    raise StorageError(f"STORAGE_BACKEND inconnu : {settings.storage_backend!r} (local | s3)")


__all__ = ["Storage", "StorageError", "StorageNotFoundError", "LocalStorage", "get_storage",
           "DATASETS", "REPORTS", "ARTIFACTS", "EXTERNAL", "BASELINES"]
