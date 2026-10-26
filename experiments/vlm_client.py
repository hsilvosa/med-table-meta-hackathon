"""Minimal client for a local llama-server (OpenAI-compatible API) with image input, shared by the spikes.

Start the server first, for example:
  llama-server -m models/qwen3.5-9b/Qwen3.5-9B-Q4_K_M.gguf --mmproj models/qwen3.5-9b/mmproj-F16.gguf \
      --port 8082 --n-gpu-layers 99 --ctx-size 8192 -fa on --jinja --parallel 1
"""

from __future__ import annotations

import base64
import json
import re
import time
import unicodedata
import urllib.request
from pathlib import Path

import cv2

URL = "http://127.0.0.1:8082/v1/chat/completions"


def ask(image: Path | str, prompt: str, max_tokens: int = 300) -> tuple[str, float]:
    """Send one image plus a prompt; thinking mode is off. Returns (answer text, seconds)."""
    _, jpg = cv2.imencode(".jpg", cv2.imread(str(image)), [cv2.IMWRITE_JPEG_QUALITY, 90])
    body = {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpg).decode()}},
            {"type": "text", "text": prompt}]}],
        "max_tokens": max_tokens, "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},  # Qwen3.5 thinks by default; far too slow for reading labels
    }
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    start = time.time()
    reply = json.load(urllib.request.urlopen(req, timeout=600))
    return reply["choices"][0]["message"]["content"], time.time() - start


def parse_json(text: str):
    """First JSON object or array in a model reply (models like to wrap it in ```json fences); None if invalid."""
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    try:
        return json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None


def norm(text: object) -> str:
    """Lower-case, accent-free, single-spaced text for loose comparisons."""
    folded = "".join(c for c in unicodedata.normalize("NFD", str(text or "").lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", folded).strip()
