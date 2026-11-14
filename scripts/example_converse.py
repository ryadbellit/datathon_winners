"""Appel Bedrock via l'API Converse (comme dans l'atelier) : un seul code, on change juste le model_id."""
import sys

import boto3
from dotenv import load_dotenv

load_dotenv(".env")

MODELES = {
    "nova": "global.amazon.nova-2-lite-v1:0",          # peu coûteux, bon pour les tests
    "sonnet": "global.anthropic.claude-sonnet-5",     # polyvalent, recommandé par l'atelier
}

client = boto3.client("bedrock-runtime", region_name="us-east-1")


def demander(question: str, model_id: str) -> str:
    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": question}]}],
        inferenceConfig={"maxTokens": 512},
    )
    usage = response["usage"]
    texte = "".join(c["text"] for c in response["output"]["message"]["content"] if "text" in c)
    return f"{texte}\n[tokens] entrée={usage['inputTokens']} sortie={usage['outputTokens']}"


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "En une phrase, qu'est-ce qu'un FNB obligataire ?"
    for nom, model_id in MODELES.items():
        print(f"=== {nom} ({model_id}) ===")
        print(demander(question, model_id), "\n")
