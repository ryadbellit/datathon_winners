"""Vérifie que les identifiants AWS du .env fonctionnent."""
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()

try:
    session = boto3.Session()
    identity = session.client("sts").get_caller_identity()
    print("Connexion AWS OK")
    print(f"  Région  : {session.region_name}")
    print(f"  Compte  : {identity['Account']}")
    print(f"  ARN     : {identity['Arn']}")
except (BotoCoreError, ClientError) as e:
    print(f"Échec de connexion AWS : {e}")
    raise SystemExit(1)
