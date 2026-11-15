"""Construit l'image, la pousse sur ECR et crée / met à jour la pile CloudFormation `alphaforge`.

    python deploy/deploy.py            # depuis la racine du dépôt, avec des identifiants AWS valides (ex. .env)

Seule la configuration NON secrète du .env est transmise (routes, prix, Guardrail, bucket) : en ligne, les droits
viennent du rôle IAM de la tâche ECS. Affiche l'adresse publique à la fin (premier déploiement : ~10 min, CloudFront).
"""
from __future__ import annotations

import base64
import subprocess
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, WaiterError
from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parent.parent
STACK, REPO = "alphaforge", "alphaforge"
CONFIG_KEYS = {  # clé du .env -> paramètre CloudFormation
    "LLM_ROUTES": "LlmRoutes", "LLM_PRICING": "LlmPricing", "LLM_MAX_TOKENS": "LlmMaxTokens",
    "GUARDRAIL_ID": "GuardrailId", "GUARDRAIL_VERSION": "GuardrailVersion", "S3_BUCKET": "BucketName", "S3_PREFIX": "BucketPrefix",
}


def run(*cmd: str, stdin: str | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=ROOT, input=stdin, text=True)


def image(session: boto3.Session) -> str:
    ecr = session.client("ecr")
    try:
        uri = ecr.describe_repositories(repositoryNames=[REPO])["repositories"][0]["repositoryUri"]
    except ClientError:
        uri = ecr.create_repository(repositoryName=REPO, imageScanningConfiguration={"scanOnPush": True})["repository"]["repositoryUri"]
    auth = ecr.get_authorization_token()["authorizationData"][0]
    user, password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    run("docker", "login", "--username", user, "--password-stdin", auth["proxyEndpoint"], stdin=password)
    tag = f"{uri}:{time.strftime('%Y%m%d-%H%M%S')}"
    run("docker", "buildx", "build", "--platform", "linux/arm64", "-t", tag, "--push", ".")
    return tag


def network(session: boto3.Session) -> tuple[str, list[str]]:
    ec2 = session.client("ec2")
    vpc = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])["Vpcs"][0]["VpcId"]
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc]}, {"Name": "default-for-az", "Values": ["true"]}])["Subnets"]
    chosen = sorted(subnets, key=lambda s: s["AvailabilityZone"])[:3]  # 3 zones suffisent (ALB : au moins 2)
    return vpc, [s["SubnetId"] for s in chosen]


def deploy(session: boto3.Session, params: dict[str, str]) -> dict[str, str]:
    cfn = session.client("cloudformation")
    args = {
        "StackName": STACK,
        "TemplateBody": (ROOT / "deploy" / "alphaforge.yaml").read_text(),
        "Parameters": [{"ParameterKey": k, "ParameterValue": v} for k, v in params.items()],
        "Capabilities": ["CAPABILITY_IAM"],
    }
    try:
        cfn.describe_stacks(StackName=STACK)
        try:
            cfn.update_stack(**args)
            waiter = "stack_update_complete"
        except ClientError as exc:
            if "No updates are to be performed" not in str(exc):
                raise
            waiter = None
    except ClientError:
        cfn.create_stack(**args, OnFailure="DELETE")
        waiter = "stack_create_complete"
    if waiter:
        print(f"CloudFormation : {waiter.replace('_', ' ')} en attente (CloudFront peut prendre ~10 min)...", flush=True)
        stack_id = cfn.describe_stacks(StackName=STACK)["Stacks"][0]["StackId"]
        try:
            cfn.get_waiter(waiter).wait(StackName=stack_id, WaiterConfig={"Delay": 20, "MaxAttempts": 120})
        except WaiterError:
            for e in cfn.describe_stack_events(StackName=stack_id)["StackEvents"]:
                if e["ResourceStatus"].endswith("_FAILED"):
                    print(f"ÉCHEC {e['LogicalResourceId']} : {e.get('ResourceStatusReason', '')}")
            raise SystemExit("Déploiement en échec (voir ci-dessus).")
    outputs = cfn.describe_stacks(StackName=STACK)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def main() -> int:
    load_dotenv(ROOT / ".env")  # identifiants du poste qui déploie (jamais transmis à la pile)
    env = dotenv_values(ROOT / ".env")
    missing = [k for k in CONFIG_KEYS if k not in ("GUARDRAIL_VERSION", "S3_PREFIX", "LLM_PRICING") and not env.get(k)]
    if missing:
        print(f"Manque dans .env : {', '.join(missing)}")
        return 1
    session = boto3.Session(region_name=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or "us-east-1")
    vpc, subnets = network(session)
    params = {CONFIG_KEYS[k]: env[k] for k in CONFIG_KEYS if env.get(k)}
    params.update(ImageUri=image(session), VpcId=vpc, SubnetIds=",".join(subnets))
    outputs = deploy(session, params)
    print(f"\nEn ligne : {outputs.get('Url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
