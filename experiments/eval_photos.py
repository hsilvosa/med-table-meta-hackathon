"""Evaluate pack identification on a folder of photos with known contents.

  .venv-app/Scripts/python.exe experiments/eval_photos.py PHOTO_DIR [--truth truth.json] [--no-network]

PHOTO_DIR holds the photos; truth.json (default PHOTO_DIR/truth.json) maps each photo name to the packs on the table, each given as
a 7-digit Codigo Nacional ("8482269" or "848226.9") or as the GS1 element string of its code. Packs that are present but not
photographable (hidden, no code on the visible side) can be listed with the suffix "!hidden" so that they count as expected misses.

Per pack present it reports one of: verified_correct, verified_wrong (the headline safety number: a pack the system claims to have
verified as something it is not), unverified (a code was found but did not verify), missed (no code found). Plus the number of
extra codes read that belong to no listed pack. Proportions come with Clopper-Pearson 95 % intervals.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, "src")
from medtable import cn as cn_module, gs1, identify  # noqa: E402
from medtable.resolve import Resolver  # noqa: E402


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval by bisection on the binomial CDF (no SciPy needed)."""
    from math import comb

    def cdf(x: int, p: float) -> float:
        return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(x + 1))

    def solve(target: float, upper: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            value = cdf(k, mid) if upper else 1 - cdf(k - 1, mid)
            if (value > target) == upper:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    if n == 0:
        return (0.0, 1.0)
    return (0.0 if k == 0 else solve(alpha / 2, upper=False), 1.0 if k == n else solve(alpha / 2, upper=True))


def as_cn(item: str) -> str:
    text = item.strip()
    if text.startswith("("):
        return gs1.parse_pack_code(text).national.cn or ""
    found = cn_module.find_cn(text)
    return found or ""


def evaluate(photo_dir: Path, truth: dict[str, list[str]], resolver: Resolver) -> dict:
    """Match by multiset of Codigo Nacional per photo: two packs of one medicine are two expected readings of that CN."""
    counts = {"verified_correct": 0, "verified_wrong": 0, "unverified": 0, "missed": 0, "hidden_expected": 0, "extra_codes": 0}
    detail = []
    for name, packs in truth.items():
        image = cv2.imread(str(photo_dir / name))
        if image is None:
            print(f"cannot read {name}", file=sys.stderr)
            continue
        readings = identify.identify(image, resolver)
        expected, hidden = Counter(), 0
        for item in packs:
            if item.endswith("!hidden"):
                hidden += 1
            else:
                expected[as_cn(item)] += 1
        counts["hidden_expected"] += hidden
        verified = Counter(r.cn for r in readings if r.status == "verified" and r.cn)
        unverified = Counter(r.cn for r in readings if r.status != "verified" and r.cn)
        for cn_value, want in expected.items():
            ok = min(want, verified[cn_value])
            partial = min(want - ok, unverified[cn_value])
            counts["verified_correct"] += ok
            counts["unverified"] += partial
            if want - ok - partial:
                counts["missed"] += want - ok - partial
                detail.append(f"{name}: missed {want - ok - partial} x {cn_value}")
        for cn_value, got in verified.items():
            surplus = got - expected.get(cn_value, 0)
            if surplus > 0:
                counts["verified_wrong"] += surplus
                detail.append(f"{name}: VERIFIED WRONG {surplus} x {cn_value}")
        counts["extra_codes"] += sum(1 for r in readings if r.status != "verified" and r.cn not in expected) + sum(1 for r in readings if not r.cn)
    return {"counts": counts, "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("photo_dir", type=Path)
    ap.add_argument("--truth", type=Path)
    args = ap.parse_args()
    truth = json.loads((args.truth or args.photo_dir / "truth.json").read_text(encoding="utf-8"))
    result = evaluate(args.photo_dir, truth, Resolver("data/cache/cima"))
    c = result["counts"]
    present = c["verified_correct"] + c["unverified"] + c["missed"]
    print(f"photos {len(truth)}; packs present and photographable {present}; hidden (not counted) {c['hidden_expected']}")
    for key, label in (("verified_correct", "verified correctly"), ("unverified", "code found, not verified"), ("missed", "no code found")):
        low, high = clopper_pearson(c[key], present)
        print(f"  {label:26} {c[key]:>4}/{present}  {c[key] / max(present, 1):6.1%}  95% CI [{low:.1%}, {high:.1%}]")
    low, high = clopper_pearson(c["verified_wrong"], c["verified_wrong"] + c["verified_correct"])
    print(f"  CONFIDENT-WRONG (verified as a pack not on the table): {c['verified_wrong']} of {c['verified_wrong'] + c['verified_correct']} verified; 95% CI upper bound {high:.1%}")
    print(f"  extra codes read that belong to no listed pack and did not verify: {c['extra_codes']}")
    for line in result["detail"][:30]:
        print("   ", line)


if __name__ == "__main__":
    main()
