import boto3
import pytest
from moto import mock_aws

from alphaforge.config import Settings
from alphaforge.storage import LocalStorage, StorageError, StorageNotFoundError, get_storage
from alphaforge.storage.s3 import S3Storage


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path, monkeypatch):
    """Les mêmes tests s'appliquent aux deux backends (S3 simulé par moto : aucun appel AWS réel)."""
    if request.param == "local":
        yield LocalStorage(tmp_path)
        return
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(var, "fake")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield S3Storage("test-bucket", "alphaforge", "us-east-1")


def test_roundtrip_bytes_and_json(storage):
    storage.put_bytes("datasets/a.bin", b"\x00\x01")
    storage.put_json("reports/r.json", {"score": 4.5, "texte": "é"})
    assert storage.get_bytes("datasets/a.bin") == b"\x00\x01"
    assert storage.get_json("reports/r.json") == {"score": 4.5, "texte": "é"}


def test_exists_list_and_not_found(storage):
    storage.put_json("reports/1.json", {})
    storage.put_json("reports/2.json", {})
    storage.put_json("datasets/x.json", {})
    assert storage.exists("reports/1.json") and not storage.exists("reports/nope.json")
    assert storage.list("reports/") == ["reports/1.json", "reports/2.json"]
    with pytest.raises(StorageNotFoundError):
        storage.get_bytes("reports/nope.json")


def test_path_traversal_is_rejected(storage):
    with pytest.raises(StorageError):
        storage.put_bytes("../evasion.txt", b"x")


def test_factory_defaults_to_local_and_validates_s3_config(tmp_path):
    assert isinstance(get_storage(Settings(_env_file=None, local_storage_dir=str(tmp_path))), LocalStorage)
    with pytest.raises(StorageError):
        get_storage(Settings(_env_file=None, storage_backend="s3"))
    with pytest.raises(StorageError):
        get_storage(Settings(_env_file=None, storage_backend="ftp"))
