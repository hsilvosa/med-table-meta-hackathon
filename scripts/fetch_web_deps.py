"""Download the front-end dependency of the 3D room (three.js, MIT) into web/vendor/. Not committed (see .gitignore).

  python scripts/fetch_web_deps.py

r170 is pinned because it is a single self-contained module file (later releases split it into several files).
"""

import hashlib
import urllib.request
from pathlib import Path

URL = "https://unpkg.com/three@0.170.0/build/three.module.js"
OUT = Path("web/vendor/three.module.js")

OUT.parent.mkdir(parents=True, exist_ok=True)
if not OUT.exists():
    with urllib.request.urlopen(URL, timeout=60) as resp:
        OUT.write_bytes(resp.read())
data = OUT.read_bytes()
assert b"REVISION" in data and b"import " not in data[:2000].replace(b"//", b""), "unexpected three.js build"
print(f"{OUT} {len(data) / 1e6:.2f} MB sha256 {hashlib.sha256(data).hexdigest()[:16]}")
