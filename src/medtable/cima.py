"""Small client for the AEMPS CIMA REST API (https://cima.aemps.es/cima/rest).

Only the standard library is used. Every call retries with exponential backoff; a 404 is raised at once.
AEMPS reuse conditions: cite the source (AEMPS / CIMA), state the date of the information, do not distort it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

API = "https://cima.aemps.es/cima/rest"
_HEADERS = {"User-Agent": "med-table-hackathon/0.1 (research prototype)"}


def fetch(url: str, *, retries: int = 4, timeout: float = 60.0) -> bytes:
    """GET `url`, retrying transient network errors with 1, 2, 4... second pauses."""
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def get_json(endpoint: str, **params: object) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    raw = fetch(f"{API}/{endpoint}?{query}")
    return json.loads(raw) if raw.strip() else {}  # CIMA answers an unknown code with an empty body, not with a 404


def iter_medicines(*, marketed_only: bool = True, pause: float = 0.2) -> Iterator[dict]:
    """Yield every medicine from /medicamentos, paging 200 at a time."""
    page = 1
    while True:
        data = get_json("medicamentos", comerc=1 if marketed_only else None, pagina=page)
        yield from data["resultados"]
        if page * data["tamanioPagina"] >= data["totalFilas"]:
            return
        page += 1
        time.sleep(pause)


def medicine_by_cn(cn: str) -> dict:
    """Look a medicine up by its 6-digit Codigo Nacional (without the check digit)."""
    return get_json("medicamento", cn=cn)


def medicine_by_nregistro(nregistro: str) -> dict:
    return get_json("medicamento", nregistro=nregistro)


def full_size_url(photo_url: str) -> str:
    """CIMA lists ~3 KB thumbnails; the same path under /full/ is the 1024 px original."""
    return photo_url.replace("/thumbnails/", "/full/")
