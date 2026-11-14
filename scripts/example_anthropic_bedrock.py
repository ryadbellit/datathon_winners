"""Appel LLM simple à Claude via Amazon Bedrock, avec les identifiants du .env."""
import os

from anthropic import AnthropicBedrockMantle
from dotenv import load_dotenv

load_dotenv(".env")

client = AnthropicBedrockMantle(aws_region=os.environ["AWS_DEFAULT_REGION"])

response = client.messages.create(
    model="anthropic.claude-opus-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Dis bonjour en une phrase et présente-toi."}],
)

for block in response.content:
    if block.type == "text":
        print(block.text)
print(f"\n[tokens] entrée={response.usage.input_tokens} sortie={response.usage.output_tokens}")
