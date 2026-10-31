"""Publish the online demo to Google Cloud Run (project med-table-demo-hs, europe-west1).

  python scripts/deploy_cloudrun.py [--tag 2]

Builds the Docker image locally, pushes it to Artifact Registry and deploys it. Needs Docker and the Google Cloud CLI logged in
(`gcloud auth login`, `gcloud auth configure-docker europe-west1-docker.pkg.dev`). Limits: at most one instance, scales to zero when
nobody uses it (no cost while idle), 4 vCPU / 4 GiB (a live scan of a whole table in about 2 s), startup CPU boost, public access without login.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT, REGION, SERVICE = "med-table-demo-hs", "europe-west1", "med-table"

ap = argparse.ArgumentParser()
ap.add_argument("--tag", default=subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
args = ap.parse_args()
image = f"{REGION}-docker.pkg.dev/{PROJECT}/medtable/demo:{args.tag}"
gcloud = shutil.which("gcloud") or os.path.expandvars(r"%LOCALAPPDATA%\Google\google-cloud-sdk\bin\gcloud.cmd")
env = dict(os.environ, CLOUDSDK_CORE_DISABLE_PROMPTS="1")


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


run("docker", "build", "-t", image, ".")
run("docker", "push", image)
run(gcloud, "run", "deploy", SERVICE, f"--project={PROJECT}", f"--region={REGION}", f"--image={image}", "--port=7860", "--memory=4Gi",
    "--cpu=4", "--cpu-boost", "--execution-environment=gen1", "--min-instances=0", "--max-instances=1", "--concurrency=40", "--timeout=600", "--session-affinity",
    "--allow-unauthenticated")
