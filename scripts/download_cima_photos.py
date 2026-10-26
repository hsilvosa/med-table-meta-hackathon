"""Download the official CIMA product photos (pack and dosage form).

  python scripts/download_cima_photos.py manifest [--all] [--out data/cima]
  python scripts/download_cima_photos.py images   [--limit N] [--workers 4] [--out data/cima]

`manifest` lists the medicines that have photos; `images` downloads them. Both steps can be re-run:
existing files are skipped and failures are appended to failed.jsonl. Photos belong to AEMPS and are
never committed to git (see THIRD_PARTY.md).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from medtable import cima  # noqa: E402


def build_manifest(out: Path, include_unmarketed: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    seen = kept = 0
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as f:
        for med in cima.iter_medicines(marketed_only=not include_unmarketed):
            seen += 1
            if not med.get("fotos"):
                continue
            kept += 1
            f.write(json.dumps({
                "nregistro": med["nregistro"],
                "nombre": med.get("nombre"),
                "labtitular": med.get("labtitular"),
                "pactivos": med.get("pactivos"),
                "forma": (med.get("formaFarmaceutica") or {}).get("nombre"),
                "comerc": med.get("comerc"),
                "fotos": [{"tipo": p["tipo"], "url": cima.full_size_url(p["url"])} for p in med["fotos"]],
            }, ensure_ascii=False) + "\n")
            if seen % 1000 == 0:
                print(f"{seen} medicines scanned, {kept} with photos", flush=True)
    print(f"manifest: {kept} of {seen} medicines have photos -> {out / 'manifest.jsonl'}")


def jobs(out: Path):
    with (out / "manifest.jsonl").open(encoding="utf-8") as f:
        for line in f:
            med = json.loads(line)
            for photo in med["fotos"]:
                yield photo["url"], out / "images" / "full" / photo["tipo"] / f"{med['nregistro']}.jpg"


def fetch_one(job: tuple[str, Path]) -> tuple[str, int]:
    url, dest = job
    if dest.exists() and dest.stat().st_size > 0:
        return "skip", 0
    data = cima.fetch(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    part.write_bytes(data)
    part.replace(dest)
    time.sleep(0.1)  # be gentle with the AEMPS server
    return "ok", len(data)


def download_images(out: Path, limit: int | None, workers: int) -> None:
    if not (out / "manifest.jsonl").exists():
        sys.exit("Run the 'manifest' step first.")
    todo = list(jobs(out))[:limit]
    counts = {"ok": 0, "skip": 0, "fail": 0}
    size = 0
    start = time.time()
    with ThreadPoolExecutor(workers) as pool, (out / "failed.jsonl").open("a", encoding="utf-8") as failed:
        futures = [(job, pool.submit(fetch_one, job)) for job in todo]
        for n, (job, fut) in enumerate(futures, 1):
            try:
                status, nbytes = fut.result()
                counts[status] += 1
                size += nbytes
            except Exception as exc:  # noqa: BLE001 - log and keep going
                counts["fail"] += 1
                failed.write(json.dumps({"url": job[0], "dest": str(job[1]), "error": repr(exc)}) + "\n")
            if n % 200 == 0 or n == len(todo):
                eta = (time.time() - start) / n * (len(todo) - n) / 60
                print(f"{n}/{len(todo)} {counts} {size / 1e6:.0f} MB, eta {eta:.1f} min", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("manifest", "images"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=Path("data/cima"))
    sub.choices["manifest"].add_argument("--all", action="store_true", help="include non-marketed medicines")
    sub.choices["images"].add_argument("--limit", type=int)
    sub.choices["images"].add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    if args.cmd == "manifest":
        build_manifest(args.out, args.all)
    else:
        download_images(args.out, args.limit, args.workers)


if __name__ == "__main__":
    main()
