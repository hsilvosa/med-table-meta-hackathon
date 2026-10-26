"""Client for the Meta Model API (https://api.meta.ai/v1, OpenAI-compatible) with a hard spending cap.

Rules built into this module:
  * Only the STANDARD tier is allowed. The "-contributor" models are cheaper because Meta may train on the
    prompts and completions; this project never sends data under those terms.
  * Every call is appended to a ledger (data/meta_usage.jsonl) with its token usage and estimated cost.
  * Before each call the worst-case cost is added to the spend so far; if that would pass the budget
    (META_BUDGET_USD, default 100, times a 0.9 safety factor) the call is refused with BudgetExceeded.
  * The token (META_TOKEN in .env) is never logged, printed or written to the ledger.
  * Anything sent leaves the machine: use only public data (CIMA photos) or fictional documents. Never send a
    real patient's prescription.

Prices: USD per 1M tokens, standard tier, https://ai.developer.meta.com/docs/pricing-rate-limits (checked 2026-10-26).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import load_env

BASE_URL = "https://api.meta.ai/v1"
# model -> (input, cached input, output) in USD per 1M tokens
PRICES = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
}
DEFAULT_MODEL = "muse-spark-1.3"
IMAGE_TOKENS_UPPER_BOUND = 6000  # pre-flight guess per image; real usage is logged after each call
SAFETY_FACTOR = 0.9
LEDGER = Path("data/meta_usage.jsonl")


class MetaAPIError(RuntimeError):
    """HTTP or protocol error from the Meta Model API (never contains the token)."""


class BudgetExceeded(RuntimeError):
    """The call was refused because it could push spending past the budget."""


@dataclass
class Reply:
    text: str
    usage: dict
    cost_usd: float
    seconds: float


def _token() -> str:
    load_env()
    token = os.environ.get("META_TOKEN", "").strip()
    if not token:
        raise MetaAPIError("META_TOKEN is empty: put it in .env (git-ignored).")
    return token


def budget_usd() -> float:
    load_env()
    return float(os.environ.get("META_BUDGET_USD", "100"))


def spent_usd(ledger: Path = LEDGER) -> float:
    if not ledger.exists():
        return 0.0
    return sum(json.loads(line)["cost_usd"] for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())


def cost_of(model: str, usage: dict) -> float:
    price_in, price_cached, price_out = PRICES[model]
    prompt = usage.get("prompt_tokens", 0)
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    return ((prompt - cached) * price_in + cached * price_cached + usage.get("completion_tokens", 0) * price_out) / 1e6


def _preflight(model: str, messages: list[dict], max_tokens: int) -> None:
    if model not in PRICES:
        raise ValueError(f"{model!r} is not an allowed model (standard tier only): {sorted(PRICES)}")
    chars = images = 0
    for message in messages:
        content = message["content"]
        for part in content if isinstance(content, list) else [{"type": "text", "text": content}]:
            if part.get("type") == "text":
                chars += len(part["text"])
            else:
                images += 1
    price_in, _, price_out = PRICES[model]
    worst = ((chars / 2.5 + images * IMAGE_TOKENS_UPPER_BOUND) * price_in + max_tokens * price_out) / 1e6
    limit = budget_usd() * SAFETY_FACTOR
    if spent_usd() + worst > limit:
        raise BudgetExceeded(f"spent ${spent_usd():.2f} + worst case ${worst:.4f} would pass ${limit:.2f} "
                             f"(budget ${budget_usd():.2f} x {SAFETY_FACTOR})")


def chat(messages: list[dict], *, model: str = DEFAULT_MODEL, max_tokens: int = 400,
         reasoning_effort: str | None = "minimal", note: str = "") -> Reply:
    """One chat completion. `reasoning_effort="minimal"` (the lowest value muse-spark-1.3 accepts) keeps hidden reasoning tokens, billed as output, low."""
    _preflight(model, messages, max_tokens)
    body: dict = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    request = urllib.request.Request(
        f"{BASE_URL}/chat/completions", json.dumps(body).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {_token()}"})
    for attempt in range(3):
        start = time.time()
        try:
            with urllib.request.urlopen(request, timeout=120) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise MetaAPIError(f"HTTP {exc.code}: {detail}") from None  # 400s are never retried
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise MetaAPIError(f"network error: {exc}") from None
            time.sleep(2 ** (attempt + 1))
    usage = data.get("usage") or {}
    cost = cost_of(model, usage)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": model, "usage": usage,
                                 "cost_usd": cost, "note": note}) + "\n")
    return Reply(data["choices"][0]["message"].get("content") or "", usage, cost, time.time() - start)


def ask_image(image: Path | str, prompt: str, *, max_tokens: int = 400, **kwargs) -> Reply:
    """Send one image (base64 data URL, user message) plus a text prompt."""
    mime = mimetypes.guess_type(str(image))[0] or "image/jpeg"
    data_url = f"data:{mime};base64," + base64.b64encode(Path(image).read_bytes()).decode()
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                             {"type": "image_url", "image_url": {"url": data_url}}]}]
    return chat(messages, max_tokens=max_tokens, **kwargs)
