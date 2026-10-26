"""Vision-language model access with two interchangeable backends.

  meta   (default)  Meta Model API, `muse-spark-1.3` standard tier, spending capped (see meta_api.py).
                    Images leave the machine: only public CIMA photos and fictional documents.
  local             Any OpenAI-compatible llama-server, e.g. Qwen3.5-9B (Q4_K_M) with its mmproj file.
                    Offline, free, nothing leaves the machine; slower and less reliable on small crops
                    (see experiments/README.md).

Choose with `VLM_BACKEND=meta|local` in .env, or pass `backend=` per call. The local server is started with:

  llama-server -m models/qwen3.5-9b/Qwen3.5-9B-Q4_K_M.gguf --mmproj models/qwen3.5-9b/mmproj-F16.gguf \
      --port 8082 --n-gpu-layers 99 --ctx-size 8192 -fa on --jinja --parallel 1

and read from `VLM_URL` (default http://127.0.0.1:8082/v1/chat/completions). Thinking mode is switched off per
request because Qwen3.5 thinks by default, which is far too slow for reading labels.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.request
from pathlib import Path

from . import meta_api
from .config import load_env
from .meta_api import MetaAPIError, Reply

DEFAULT_LOCAL_URL = "http://127.0.0.1:8082/v1/chat/completions"


def backend_name(backend: str | None = None) -> str:
    load_env()
    name = (backend or os.environ.get("VLM_BACKEND", "meta")).strip().lower()
    if name not in ("meta", "local"):
        raise ValueError(f"VLM_BACKEND must be 'meta' or 'local', got {name!r}")
    return name


def _ask_local(image: Path | str, prompt: str, max_tokens: int) -> Reply:
    mime = mimetypes.guess_type(str(image))[0] or "image/jpeg"
    data_url = f"data:{mime};base64," + base64.b64encode(Path(image).read_bytes()).decode()
    body = {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url}},
            {"type": "text", "text": prompt}]}],
        "max_tokens": max_tokens, "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    url = os.environ.get("VLM_URL", DEFAULT_LOCAL_URL)
    request = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            data = json.load(resp)
    except OSError as exc:
        raise MetaAPIError(f"local VLM server not reachable at {url}: {exc}") from None
    return Reply(data["choices"][0]["message"].get("content") or "", data.get("usage") or {}, 0.0, time.time() - start)


def ask_image(image: Path | str, prompt: str, *, backend: str | None = None, max_tokens: int = 400,
              note: str = "") -> Reply:
    """Send one image and a prompt to the selected backend. Cost is 0 for the local backend."""
    if backend_name(backend) == "local":
        return _ask_local(image, prompt, max_tokens)
    return meta_api.ask_image(image, prompt, max_tokens=max_tokens, note=note)


def parse_json(text: str):
    """First JSON object or array in a reply (models wrap it in ```json fences); None when it does not parse."""
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    try:
        return json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None
