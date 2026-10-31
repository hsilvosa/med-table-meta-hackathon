"""Publish the online demo to a Hugging Face Space (Docker).

  uv run --with huggingface_hub python scripts/deploy_space.py [--space hsilvosa/med-table]

Uses the Hugging Face login already stored on this machine (`hf auth login`); no token is read or printed here. Only files tracked by
git are uploaded (never .env, data/ or models/), without what the demo does not need, and with deploy/SPACE_README.md as the Space's
README (its header tells Hugging Face to build the Dockerfile).
"""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
SKIP = (".github/", "docs/", "media/", "experiments/", "tests/", "README.md", "PLAN.md")

ap = argparse.ArgumentParser()
ap.add_argument("--space", default="hsilvosa/med-table")
args = ap.parse_args()

files = [f for f in subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
         if not f.startswith(SKIP)]
with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp)
    for f in files:
        (stage / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, stage / f)
    shutil.copy2(ROOT / "deploy" / "SPACE_README.md", stage / "README.md")
    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    commit = api.upload_folder(folder_path=stage, repo_id=args.space, repo_type="space", delete_patterns=["*"],
                               commit_message="Deploy from " + subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                                                              capture_output=True, text=True).stdout.strip())
print(f"{len(files)} files uploaded: https://huggingface.co/spaces/{args.space}  ({commit.oid[:7]})")
